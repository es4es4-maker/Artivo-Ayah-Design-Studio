#!/usr/bin/env python3
"""Select 200 NEW unique uthmani verses (themes: paradise/mercy/forgiveness/guidance/beauty)
from quran-json (tanzil uthmani) and extend assets/verses.json to A001..A300.
Integrity: text is copied verbatim from source verse.text — zero editing.
Plate-aware ordering so long verses land on roomy portrait plates and short ones
on tighter/landscape plates.
"""
import json, re

ROOT = '/home/user/Artivo-Ayah-Design-Studio'
q = json.load(open(f'{ROOT}/tools/node_modules/quran-json/dist/quran.json'))
verses = json.load(open(f'{ROOT}/assets/verses.json'))

B00 = [v for v in verses if v['key'] == 'B00']
core = {v['key']: v for v in verses if re.fullmatch(r'A\d{3}', v['key']) and int(v['key'][1:]) <= 100}
old_bonus = {v['key']: v for v in verses if re.fullmatch(r'A\d{3}', v['key']) and int(v['key'][1:]) >= 101}
used_refs = {v['ref'] for v in core.values()}

INDIC = '٠١٢٣٤٥٦٧٨٩'
def to_indic(n): return ''.join(INDIC[int(d)] for d in str(n))

def norm(t):
    return t.replace('\u06E9', '\u06D6')

# ---- theme keywords (uthmani-aware) ----
THEMES = {
  'paradise':    ['جَنَّٰت', 'ٱلۡجَنَّة', 'ٱلۡفِرۡدَوۡس', 'نَعِيم', 'ٱلۡفَوۡز', 'جَنَّة', 'خَٰلِدِينَ'],
  'mercy':       ['رَّحۡمَٰن', 'رَحۡمَة', 'رَّحِيم', 'رَحِيمٌۢ', 'رَّحۡمَٰنِ', 'رَحۡمَٰنُ', 'رَحِيمًا'],
  'forgiveness': ['غَفَر', 'غَفُور', 'غَفَّار', 'مَغۡفِر', 'مَّغۡفِر', 'تَوَّاب', 'تُوبُوٓاْ', 'ٱلتَّوۡبَة', 'عَفَا', 'ذُنُوب', 'ذَنۢب', 'غُفِرَ'],
  'guidance':    ['ٱلۡهُدَىٰ', 'هَدَىٰ', 'يَهۡدِي', 'ٱهۡدِنَا', 'ٱلصِّرَٰط', 'ضَلَٰل', 'هَٰدِي', 'مُهۡتَدِي'],
  'beauty':      ['نُور', 'صَبۡر', 'شَاكِر', 'شُكۡر', 'سَلَٰم', 'بُشۡرَىٰ', 'سَكِينَة', 'تَوَكَّل', 'قُلُوب', 'ٱلۡبِرّ', 'خَيۡر', 'رِزۡق', 'مُتَّقِين', 'أَحۡسَن', 'بِـَٔايَٰتِ', 'كَرِيم'],
}

def theme_of(text):
    hits = []
    for t, kws in THEMES.items():
        if any(k in text for k in kws):
            hits.append(t)
    return hits

def theme_score(text):
    s = 0
    for t, kws in THEMES.items():
        s += sum(text.count(k) for k in kws)
    return s

# ---- collect candidate verses ----
cands = []
for ch in q:
    for v in ch['verses']:
        ref = f"{ch['id']}:{v['id']}"
        if ref in used_refs:
            continue
        t = v['text'].strip()
        if t.startswith('۞'):
            t = t[1:].strip()
        w = len(t.split())
        if w < 4 or w > 38:
            continue
        hits = theme_of(t)
        if not hits:
            continue
        cands.append({
            'ref': ref, 'sura': ch['id'], 'ayah': v['id'], 'surah': ch['name'],
            'text': t, 'words': w, 'score': theme_score(t), 'theme': hits[0],
        })

# old bonus famous refs must be in (force select)
famous = sorted({v['ref'] for v in old_bonus.values()} - used_refs)
by_ref = {c['ref']: c for c in cands}
must = [by_ref[r] for r in famous if r in by_ref]
must_refs = {c['ref'] for c in must}

# rank: score desc, then sura diversity — greedily pick top 200 incl. must-haves
cands.sort(key=lambda c: (-c['score'], c['sura'], c['ayah']))
picked = []
seen = set()
for c in must:
    picked.append(c); seen.add(c['ref'])
for c in cands:
    if len(picked) >= 200:
        break
    if c['ref'] in seen:
        continue
    picked.append(c); seen.add(c['ref'])
print('picked:', len(picked))

# ---- plate-aware assignment: new keys A101..A300 land plate by (key-1)%10
# plates: 1,3,5 roomy portrait; 2,4,6,8 mid portrait; 7,9,10 landscape (tighter height)
SLOTS = [  # allowed max words per plate slot
    {1: 38, 3: 34, 5: 34, 2: 30, 4: 30, 6: 30, 8: 30, 7: 18, 9: 18, 10: 20},
]
def plate_of_key(knum): return ((knum - 1) % 10) + 1

# sort candidates: long desc, short asc interleave, so each plate row gets variety
long_vs  = [c for c in picked if c['words'] > 24]
mid_vs   = [c for c in picked if 14 < c['words'] <= 24]
short_vs = [c for c in picked if c['words'] <= 14]
print('long/mid/short:', len(long_vs), len(mid_vs), len(short_vs))

assign = {}  # keynum -> candidate
def take(pool, cond):
    for i, c in enumerate(pool):
        if cond(c):
            return pool.pop(i)
    return pool.pop(0) if pool else None

for knum in range(101, 301):
    pid = plate_of_key(knum)
    if pid in (7, 9):
        c = take(short_vs, lambda c: True) or take(mid_vs, lambda c: True) or take(long_vs, lambda c: c['words'] <= 30)
    elif pid == 10:
        c = take(short_vs, lambda c: True) or take(mid_vs, lambda c: True) or take(long_vs, lambda c: c['words'] <= 32)
    elif pid == 1:
        c = take(long_vs, lambda c: True) or take(mid_vs, lambda c: True) or take(short_vs, lambda c: True)
    else:
        c = take(mid_vs, lambda c: True) or take(long_vs, lambda c: c['words'] <= 30) or take(short_vs, lambda c: True)
    if c is None:
        raise SystemExit(f'no candidate left for key {knum}')
    assign[knum] = c

# pin Ayat al-Kursi (2:255) to a roomy plate slot on D01 if present
for knum, c in assign.items():
    if c['ref'] == '2:255':
        if plate_of_key(knum) != 1:
            for k2 in range(101, 301, 10):  # D01 slots
                other = assign[k2]
                assign[k2], assign[knum] = c, other
                break
        break

out = B00 + [core[f'A{i:03d}'] for i in range(1, 101)]
for knum in range(101, 301):
    c = assign[knum]
    out.append({
        'key': f'A{knum:03d}',
        'ref': c['ref'],
        'theme': c['theme'],
        'text': c['text'],                       # verbatim uthmani
        'caption': f"{c['surah']} : {to_indic(c['ayah'])}",
        'verified': 'tanzil/quran-json uthmani',
    })

refs = [v['ref'] for v in out if v['key'].startswith('A')]
assert len(refs) == 300 and len(set(refs)) == 300, 'duplicate or missing refs'
json.dump(out, open(f'{ROOT}/assets/verses.json', 'w'), ensure_ascii=False, indent=1)
print('verses.json ->', len(out), 'entries (B00 + A001..A300)')
# quick distribution report
from collections import Counter
print(Counter(v['theme'] for v in out if v['key'].startswith('A')))
worst = [(int(v['key'][1:]), len(v['text'].split())) for v in out if v['key'].startswith('A') and int(v['key'][1:]) % 10 in (7, 9, 0)]
print('longest on landscape plates:', sorted(worst, key=lambda x: -x[1])[:6])
