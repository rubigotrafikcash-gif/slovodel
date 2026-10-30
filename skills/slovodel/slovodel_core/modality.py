"""Bounded predicate-local modal risk screening, not a Russian semantic parser.

Do not pair a lost permission with an obligation attached to another action.
Unknown inflections, ambiguous alignments and large candidate sets get review.
No literal action, name or source fragment is included in the public findings.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

MAY = frozenset(('может', 'могут', 'можете', 'можем', 'могу', 'можешь',
                 'мог', 'могла', 'могло', 'могли', 'можно', 'вправе',
                 'допускается', 'разрешается'))
MUST = frozenset(('должен', 'должна', 'должно', 'должны', 'обязан', 'обязана',
                  'обязаны', 'обязательно', 'обязательна', 'обязателен',
                  'обязательны', 'необходимо', 'требуется', 'нужно'))
_WORD = re.compile(r'[^\W\d_]+', re.UNICODE)
_SPLIT = re.compile(r'[.!?;,\r\n]+|\s+(?:а|но|зато)\s+', re.IGNORECASE)
_LINK = re.compile(r'(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+', re.IGNORECASE)
_UNCERTAIN = frozenset(('возможно', 'вероятно', 'предположительно', 'возможность',
                       'возможности', 'планируют', 'планировали', 'планируется',
                       'планировалось', 'намерены', 'готовятся', 'готовились'))
_AUX = frozenset(('быть', 'стать'))
_STOP = MAY | MUST | _UNCERTAIN | frozenset((
    'этого', 'этой', 'этом', 'того', 'также', 'чтобы', 'если', 'после',
    'будет', 'будут', 'было', 'были', 'была', 'словам', 'сейчас', 'тогда'))
_ENDINGS = ('ть', 'ться', 'ти', 'л', 'ла', 'ло', 'ли', 'лся', 'лась', 'лось',
            'лись', 'ет', 'ют', 'ут', 'ит', 'ят', 'ется', 'ются', 'утся',
            'ится', 'ятся', 'т', 'ты', 'та', 'то')


@dataclass(frozen=True)
class _Claim:
    mode: str
    action: str | None
    context: frozenset[str]


def _base(word: str) -> str | None:
    if word in _AUX:
        return None
    for ending in ('ться', 'ть', 'ти'):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]
    return None


def _clauses(text: str) -> list[tuple[tuple[str, ...], tuple[_Claim, ...]]]:
    text = _LINK.sub(' ', text.casefold().replace('ё', 'е'))
    result = []
    for part in _SPLIT.split(text):
        words = tuple(_WORD.findall(part))
        if not words:
            continue
        claims = []
        for i, word in enumerate(words):
            mode = 'may' if word in MAY else 'must' if word in MUST else None
            if mode is None:
                continue
            # Auxiliary words such as "могли бы" and "нужно было" are skipped.
            nearby = words[i+1:i+7] + tuple(reversed(words[max(0, i-4):i]))
            action = (next((b for w in nearby if (b := _base(w)) is not None), None)
                      if len(words) <= 256 else None)
            context = frozenset(w[:5] for w in words[max(0, i-8):i+10] if len(w) >= 4
                                and w not in _STOP
                                and not (action and w.startswith(action)))
            claims.append(_Claim(mode, action, context))
        result.append((words, tuple(claims)))
    return result


def changes(before: str, after: str) -> tuple[int, int, str]:
    """Return aggregate removed/added risks and strongest severity.

    Matched predicate loss or may/must flip blocks. An unaligned/uncertain
    predicate is only a review finding; it must not be silently approved.
    Adding an unrelated instruction cannot flip a different modal claim.
    """
    left, right = _clauses(before), _clauses(after)
    existing = {c for _, claims in right for c in claims}
    index: dict[str, set[int]] = defaultdict(set)
    for number, (words, _) in enumerate(right):
        for word in set(words):
            index[word].add(number)
    removed = added = 0
    blocking = False
    evaluated: dict[_Claim, tuple[int, int, bool]] = {}
    for _, claims in left:
        for claim in claims:
            if claim in existing:
                continue
            if claim in evaluated:
                r, a, block = evaluated[claim]
                removed += r
                added += a
                blocking |= block
                continue
            candidates: set[int] = set()
            if claim.action:
                for ending in _ENDINGS:
                    candidates.update(index.get(claim.action + ending, ()))
                    if len(candidates) > 64:
                        break
            outcome = (1, 0, False)
            if candidates and len(candidates) <= 64:
                scored = []
                for number in sorted(candidates):
                    words, new_claims = right[number]
                    context = {w[:5] for w in words if len(w) >= 4 and w not in _STOP
                               and not w.startswith(claim.action)}
                    score = len(context & claim.context)
                    # Do not bind two objects merely because their verb repeats.
                    if claim.context and context and score == 0:
                        continue
                    modes = {c.mode for c in new_claims if c.action == claim.action}
                    uncertain = bool(_UNCERTAIN.intersection(words))
                    scored.append((score, modes, uncertain))
                if scored:
                    best = max(s[0] for s in scored)
                    matches = [(m, u) for score, m, u in scored if score == best]
                    if all(claim.mode in m for m, _ in matches):
                        outcome = (0, 0, False)
                    elif len(matches) == 1:
                        modes, uncertain = matches[0]
                        outcome = (1, int(bool(modes)), not uncertain)
            evaluated[claim] = outcome
            r, a, block = outcome
            removed += r
            added += a
            blocking |= block
    return removed, added, 'blocker' if blocking else 'review'
