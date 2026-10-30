"""Bounded comparison forms; never rewrite stored source or exact terms."""
import re
from datetime import date

MONTHS = 'января февраля марта апреля мая июня июля августа сентября октября ноября декабря'.split()
ONES = 'ноль один два три четыре пять шесть семь восемь девять'.split()
TEENS = 'десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать семнадцать восемнадцать девятнадцать'.split()
TENS = dict(zip('двадцать тридцать сорок пятьдесят шестьдесят семьдесят восемьдесят девяносто'.split(),range(20,100,10)))
HUNDREDS = dict(zip('сто двести триста четыреста пятьсот шестьсот семьсот восемьсот девятьсот'.split(),range(100,1000,100)))
VALUES = {w:i for i,w in enumerate(ONES)} | {w:i+10 for i,w in enumerate(TEENS)} | TENS | HUNDREDS | {'одна':1,'одно':1,'две':2,'тысяча':1000,'тысячу':1000,'тысячи':1000,'тысяч':1000}
_ORD_STEMS = {1:'перв',2:'втор',4:'четвёрт',5:'пят',6:'шест',7:'седьм',8:'восьм',9:'девят',10:'десят',11:'одиннадцат',12:'двенадцат',13:'тринадцат',14:'четырнадцат',15:'пятнадцат',16:'шестнадцат',17:'семнадцат',18:'восемнадцат',19:'девятнадцат',20:'двадцат',30:'тридцат',40:'сороков',50:'пятидесят',60:'шестидесят',70:'семидесят',80:'восьмидесят',90:'девяност'}
ORDINALS = {stem+end:n for n,stem in _ORD_STEMS.items() for end in ('ый','ой','ого')}
ORDINALS.update({'третий':3,'третьего':3,'четвертого':4,'четвертый':4})


def _cardinal(words):
    total = part = 0
    previous = 1000
    scaled = False
    for word in words:
        value = VALUES[word]
        if value == 1000:
            if scaled or part > 999: return None
            if previous == 1 and part == 0: return None
            total = (part or 1)*1000;part=0;previous=1000;scaled=True
        else:
            rank = 100 if value >= 100 else 10 if value >= 10 else 1
            if rank >= previous or (previous == 10 and part % 100 >= 10 and part % 100 < 20): return None
            part += value;previous=rank
    return total+part


def numbers(text):
    matches=[m for m in re.finditer(r'\w+',text) if m.group().casefold() in VALUES or m.group().casefold() in ORDINALS]
    parts=[];end=0;i=0
    while i<len(matches):
        j=i+1
        while j<len(matches) and text[matches[j-1].end():matches[j].start()].isspace(): j+=1
        group=matches[i:j];words=[m.group().casefold() for m in group]
        value=None
        if len(words)>1:
            if words[-1] in ORDINALS:
                # Compound ordinal years: the cardinal prefix is an exact multiple
                # of the final ordinal's order. Never treat standalone ordinals as cardinals.
                prefix=_cardinal(words[:-1]);last=ORDINALS[words[-1]]
                if (prefix and prefix>=1000 and prefix+last<=2999
                        and prefix% (100 if last>=10 else 10)==0
                        and re.match(r'(?iu)\s+(?:год\w*|по\b)',text[group[-1].end():])):
                    value=prefix+last
            elif all(w in VALUES for w in words): value=_cardinal(words)
        if value is not None:
            parts.extend((text[end:group[0].start()],str(value)));end=group[-1].end()
        i=j
    parts.append(text[end:]);return ''.join(parts)


def date_key(raw):
    raw=' '.join(raw.casefold().split())
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw): return date.fromisoformat(raw).isoformat()
        m=re.fullmatch(r'(\d{1,2})[./](\d{1,2})[./](\d{4})',raw)
        if m: return date(int(m[3]),int(m[2]),int(m[1])).isoformat()
        m=re.fullmatch(r'(\d{1,2})\s+([а-я]+)\s+(\d{4})(?:\s*г(?:ода|\.)?)?',raw)
        if m and m[2] in MONTHS: return date(int(m[3]),MONTHS.index(m[2])+1,int(m[1])).isoformat()
    except ValueError: pass
    return raw


def _prepare_plain(text):
    text=numbers(text)
    # Conventional standalone article section labels are layout, not proper names.
    # Keep the words; never exempt a heading with names, values or extra content.
    text=re.sub(r'(?m)^[ \t]*(?:МАТЕРИАЛ(?:Ы)? И МЕТОДЫ|РЕЗУЛЬТАТЫ|ОБСУЖДЕНИЕ|ЗАКЛЮЧЕНИЕ)[ \t]*$',
                lambda m:m.group().lower(),text)
    # Only typographic variants of the same numeric endpoints, not arbitrary dashes.
    text=re.sub(r'(?<![\w–—-])(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)(?![\w–—-])',
                r'\1–\2',text)
    # Same stated unit/rate, no conversion or inferred period.
    text=re.sub(r'(?iu)(?<!\w)(\d+(?:[.,]\d+)?)\s*(?:ч\s*/\s*сут(?:ки)?|час(?:а|ов)?\s+в\s+сутки)(?!\w)',
                r'\1 часов в сутки',text)
    if 'гг.' in text.casefold():
        text=re.sub(r'(?iu)(\b\d{4})\s+гг\.',r'\1 год.',text)
    # Shared monetary unit in a tightly bounded two-amount list.
    if 'тыс.' in text.casefold():
        text=re.sub(r'(?iu)(?<!\w)(\d+(?:[.,]\d+)?)\s+(тыс\.)\s+и\s+(\d+(?:[.,]\d+)?)\s+тыс\.\s+(руб(?:\.|лей|ля|ль)?)(?!\w)',
                    r'\1 \2 \4 и \3 тыс. \4',text)
    return text


def prepare(text):
    if '://' not in text and 'www.' not in text.casefold() and '@' not in text:
        return _prepare_plain(text)
    protected=re.compile(r'(?iu)(?:https?://|www\.)[^\s<>]+|[\w.+-]+@[\w.-]+\.[a-zа-яё]{2,}')
    parts=[];end=0
    for m in protected.finditer(text):
        parts.extend((_prepare_plain(text[end:m.start()]),m.group()));end=m.end()
    parts.append(_prepare_plain(text[end:]));return ''.join(parts)


def paired_names(before, after, person):
    """Only complete two-token spans, with exact reversal or peer-backed -ом forms."""
    spans=[list(person.finditer(t)) for t in (before,after)]
    replacements=[{},{}]
    def variants(raw):
        words=raw.split(); choices=[[w,w[:-2]] if len(w)>=7 and w.endswith('ом') else [w] for w in words]
        return {' '.join(sorted((x,y))) for x in choices[0] for y in choices[1]}
    lookup={}
    for b in {m.group() for m in spans[1]}:
        for key in variants(b): lookup.setdefault(key,set()).add(b)
    pairs={}
    for raw in {m.group() for m in spans[0]}:
        candidates=set().union(*(lookup.get(k,set()) for k in variants(raw)))
        if len(candidates)==1:
            other=candidates.pop()
            keys=variants(raw)&variants(other)
            if keys: pairs[raw]=(other,min(keys,key=len))
    for a in spans[0]:
        if a.group() in pairs:
            other,canonical=pairs[a.group()]
            replacements[0][a.span()]=canonical
    reverse={other:canonical for other,canonical in pairs.values()}
    for b in spans[1]:
        if b.group() in reverse: replacements[1][b.span()]=reverse[b.group()]
    result=[]
    for text, mapping in zip((before,after),replacements):
        for (start,end),value in sorted(mapping.items(),reverse=True): text=text[:start]+value+text[end:]
        result.append(text)
    return result


def paired(before, after, person):
    before,after=prepare(before),prepare(after)
    # A stated count may summarize the very same explicit adjective list.
    pat=re.compile(r'(?iu)(?P<count>четыр[её]х|четыре)\s+подходов:\s*(?P<items>[а-яё]+(?:,\s*[а-яё]+){2}\s+и\s+[а-яё]+)')
    for match in list(pat.finditer(after))[::-1]:
        body=match['items']
        if re.search(r'(?iu)'+re.escape(body)+r'\s+подходов',before):
            after=after[:match.start('count')]+after[match.end('count'):]
    return paired_names(before,after,person)
