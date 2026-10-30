"""Corroborate additions against explicitly supplied, attributed context.

This does not verify the source or excuse removals, substitutions or bindings.
Raw A8 findings remain unchanged in the workflow report.
"""
import hashlib
import json
import re
from . import fact_guard as fg

ALLOWED = {'date', 'number', 'proper_name', 'person', 'organization', 'calendar'}


def review(before, after, document, findings):
    raw, text = document
    records = json.loads(text)
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise ValueError('CONTEXT_INVALID')
    for item in records:
        if (not isinstance(item, dict) or set(item) != {'text', 'source'} or
                any(not isinstance(item[k], str) or not item[k].strip()
                    for k in ('text', 'source')) or
                len(item['text']) > 4000 or len(item['source']) > 512):
            raise ValueError('CONTEXT_INVALID')
    # Reference numbers are not inferred to be expendable from typography alone.
    # Only explicit Wikipedia provenance allows review of attached references.
    references = re.compile(r'(?<=[а-яё».)])\[\d{1,3}\]', re.I)
    cited = (bool(references.search(before)) and
             any(re.match(r'https://(?:[a-z]+\.)?wikipedia\.org/wiki/', item['source'])
                 for item in records))
    if cited:
        before, after = references.sub('', before), references.sub('', after)
    before, _ = fg._comparison_glyphs(before, after)
    after, _ = fg._comparison_glyphs(after, before)
    from .equivalence import paired, prepare
    before, after = paired(before, after, fg.PERSON)
    seeds, base = fg._shared_context(before, after)
    left = fg.inventory(before, (), seeds, base)
    right = fg.inventory(after, (), seeds, base)
    # Separate records prevent invented names assembled across source boundaries.
    supplied = {kind: fg.Counter() for kind in ALLOWED}
    for item in records:
        # Match complete names against the revision too (including reversed order).
        contextual, _ = paired_names_for_context(prepare(item['text']), after)
        inv = fg.inventory(contextual, (), seeds, base)
        for kind in ALLOWED:
            supplied[kind].update(inv[kind])
    supported, unresolved = [], []
    for finding in findings:
        if finding['severity'] != 'blocker':
            continue
        kind = finding['kind']
        additions = right[kind] - left[kind]
        if (cited and kind in ('number', 'binding') and left[kind] == right[kind]
                and all(left[k] == right[k] for k in fg._NUMERIC_KINDS)):
            supported.append(kind)
        elif (kind in ALLOWED and finding['removed_count'] == 0 and additions
                and not (additions - supplied[kind])):
            supported.append(kind)
        else:
            unresolved.append(kind)
    return dict(context_sha256=hashlib.sha256(raw).hexdigest(),
                trust='supplied_context_not_independently_verified',
                supported_addition_kinds=supported,
                unresolved_blocker_kinds=unresolved)


def paired_names_for_context(context, after):
    from .equivalence import paired_names
    return paired_names(context, after, fg.PERSON)
