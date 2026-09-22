#!/usr/bin/env python3
"""Generate the static reading-plan tables for the Daily Bible tab.

Reads tools/nt_daily_readings.txt (hand-authored, pericope-based, 365 lines),
validates it against the standard (KJV/WEB) verse counts embedded below, and
emits DAILY_NT_PLAN / DAILY_PSALM_PLAN / DAILY_PROV_PLAN as both a JS snippet
(web/static/app.js) and a Python snippet (dashboard.py). No network needed.

    python3 tools/gen_daily_plan.py            # print both snippets
    python3 tools/gen_daily_plan.py --js       # JS only
    python3 tools/gen_daily_plan.py --py       # Python only

Each table entry is [label, segments] where segments is a list of
[book_id, chapter, from_verse, to_verse], every segment within one chapter.

  NT       — from nt_daily_readings.txt; 365 entries.
  Psalms   — 1..150 in order; Psalm 119 split over 4 days along its acrostic
             stanzas (6+6+5+5 stanzas). 153 entries.
  Proverbs — whole book (915 verses) over 365 days: 2–3 verses per day,
             never spanning a chapter.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NT_FILE = os.path.join(HERE, "nt_daily_readings.txt")
DAYS = 365

# Verses per chapter (standard KJV/WEB versification).
VERSES = {
    "MAT": [25,23,17,25,48,34,29,34,38,42,30,50,58,36,39,28,27,35,30,34,46,46,39,51,46,75,66,20],
    "MRK": [45,28,35,41,43,56,37,38,50,52,33,44,37,72,47,20],
    "LUK": [80,52,38,44,39,49,50,56,62,42,54,59,35,35,32,31,37,43,48,47,38,71,56,53],
    "JHN": [51,25,36,54,47,71,53,59,41,42,57,50,38,31,27,33,26,40,42,31,25],
    "ACT": [26,47,26,37,42,15,60,40,43,48,30,25,52,28,41,40,34,28,41,38,40,30,35,27,27,32,44,31],
    "ROM": [32,29,31,25,21,23,25,39,33,21,36,21,14,23,33,27],
    "1CO": [31,16,23,21,13,20,40,13,27,33,34,31,13,40,58,24],
    "2CO": [24,17,18,18,21,18,16,24,15,18,33,21,14],
    "GAL": [24,21,29,31,26,18],
    "EPH": [23,22,21,32,33,24],
    "PHP": [30,30,21,23],
    "COL": [29,23,25,18],
    "1TH": [10,20,13,18,28],
    "2TH": [12,17,18],
    "1TI": [20,15,16,16,25,21],
    "2TI": [18,26,17,22],
    "TIT": [16,15,15],
    "PHM": [25],
    "HEB": [14,18,19,16,14,20,28,13,28,39,40,29,25],
    "JAS": [27,26,18,17,20],
    "1PE": [25,25,22,19,14],
    "2PE": [21,22,18],
    "1JN": [10,29,24,21,21],
    "2JN": [13],
    "3JN": [14],
    "JUD": [25],
    "REV": [20,29,22,11,14,17,17,13,21,11,19,17,18,20,8,21,18,24,21,15,27,21],
    "PRO": [33,22,35,27,23,35,27,36,18,32,31,28,25,35,33,33,28,24,29,30,31,29,35,34,28,28,27,28,27,33,31],
    "PSA": {119: 176},
}
NT_ORDER = ["MAT","MRK","LUK","JHN","ACT","ROM","1CO","2CO","GAL","EPH","PHP","COL",
            "1TH","2TH","1TI","2TI","TIT","PHM","HEB","JAS","1PE","2PE","1JN","2JN","3JN","JUD","REV"]
NAMES = {
    "MAT":"Matthew","MRK":"Mark","LUK":"Luke","JHN":"John","ACT":"Acts","ROM":"Romans",
    "1CO":"1 Corinthians","2CO":"2 Corinthians","GAL":"Galatians","EPH":"Ephesians",
    "PHP":"Philippians","COL":"Colossians","1TH":"1 Thessalonians","2TH":"2 Thessalonians",
    "1TI":"1 Timothy","2TI":"2 Timothy","TIT":"Titus","PHM":"Philemon","HEB":"Hebrews",
    "JAS":"James","1PE":"1 Peter","2PE":"2 Peter","1JN":"1 John","2JN":"2 John","3JN":"3 John",
    "JUD":"Jude","REV":"Revelation","PSA":"Psalm","PRO":"Proverbs",
}
assert sum(sum(v) for k, v in VERSES.items() if k in NT_ORDER) == 7957
assert sum(VERSES["PRO"]) == 915

EN_DASH = "–"


def chapters_of(book):
    return len(VERSES[book])


def verses_in(book, chapter):
    return VERSES[book][chapter - 1]


def label_for(segments):
    """Human label: 'Matthew 1', 'Matthew 13:44–14:12', 'Jude', '2 John; 3 John'."""
    by_book = []
    for seg in segments:
        if by_book and by_book[-1][0] == seg[0]:
            by_book[-1][1].append(seg)
        else:
            by_book.append((seg[0], [seg]))
    parts = []
    for book, segs in by_book:
        name = NAMES[book]
        first, last = segs[0], segs[-1]
        whole = first[2] == 1 and last[3] == verses_in(book, last[1])
        if chapters_of(book) == 1:
            parts.append(name if whole else f"{name} {first[2]}{EN_DASH}{last[3]}")
        elif first[1] == last[1]:
            if whole:
                parts.append(f"{name} {first[1]}")
            elif first[2] == last[3]:
                parts.append(f"{name} {first[1]}:{first[2]}")
            else:
                parts.append(f"{name} {first[1]}:{first[2]}{EN_DASH}{last[3]}")
        else:
            parts.append(f"{name} {first[1]}:{first[2]}{EN_DASH}{last[1]}:{last[3]}")
    return "; ".join(parts)


RANGE_RE = re.compile(r"^([1-3]?[A-Z]{2,3}) (\d+):(\d+)-(?:(\d+):)?(\d+)$")


def parse_range(text):
    """'MAT 13:44-14:12' -> [['MAT',13,44,58], ['MAT',14,1,12]]"""
    m = RANGE_RE.match(text.strip())
    if not m:
        raise ValueError(f"bad range: {text!r}")
    book, c1, v1, c2, v2 = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4), int(m.group(5))
    c2 = int(c2) if c2 else c1
    segs = []
    for c in range(c1, c2 + 1):
        a = v1 if c == c1 else 1
        z = v2 if c == c2 else verses_in(book, c)
        segs.append([book, c, a, z])
    return segs


def nt_plan():
    plan = []
    with open(NT_FILE) as f:
        for lineno, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            segs = []
            for part in line.split(";"):
                segs.extend(parse_range(part))
            plan.append([label_for(segs), segs])
    # Every NT verse exactly once, in canonical order
    expect = [(b, c, v) for b in NT_ORDER for c in range(1, chapters_of(b) + 1)
              for v in range(1, verses_in(b, c) + 1)]
    got = [(b, c, v) for _, segs in plan for b, c, a, z in segs for v in range(a, z + 1)]
    if got != expect:
        for i, (g, e) in enumerate(zip(got, expect)):
            if g != e:
                raise SystemExit(f"NT plan diverges at verse #{i+1}: got {g}, expected {e}")
        raise SystemExit(f"NT plan covers {len(got)} verses, expected {len(expect)}")
    if len(plan) != DAYS:
        raise SystemExit(f"NT plan has {len(plan)} days, expected {DAYS}")
    return plan


def psalm_plan():
    plan = []
    for ch in range(1, 151):
        if ch == 119:
            # 22 stanzas of 8 verses; 6+6+5+5 stanzas per day
            for a, z in [(1, 48), (49, 96), (97, 136), (137, 176)]:
                plan.append([f"Psalm 119:{a}{EN_DASH}{z}", [["PSA", 119, a, z]]])
        else:
            plan.append([f"Psalm {ch}", [["PSA", ch, None, None]]])
    assert len(plan) == 153
    return plan


def split_range(n, k):
    """Split verses 1..n into k near-equal contiguous ranges."""
    out, start = [], 1
    for i in range(k):
        size = n // k + (1 if i < n % k else 0)
        out.append((start, start + size - 1))
        start += size
    return out


def prov_plan():
    verses = VERSES["PRO"]
    total = sum(verses)
    # Largest-remainder apportionment of 365 portions across chapters.
    quotas = [v * DAYS / total for v in verses]
    ks = [int(q) for q in quotas]
    for i in sorted(range(31), key=lambda i: quotas[i] - int(quotas[i]), reverse=True)[: DAYS - sum(ks)]:
        ks[i] += 1
    plan = []
    for ch, (v, k) in enumerate(zip(verses, ks), start=1):
        for a, z in split_range(v, k):
            segs = [["PRO", ch, a, z]]
            plan.append([label_for(segs), segs])
    assert len(plan) == DAYS, len(plan)
    sizes = {z - a + 1 for _, segs in plan for _, _, a, z in segs}
    assert sizes <= {2, 3}, sizes
    return plan


def fmt(rows, py):
    null = "None" if py else "null"
    def cell(x):
        if x is None:
            return null
        return f'"{x}"' if isinstance(x, str) else str(x)
    lines = []
    for label, segs in rows:
        seg_txt = ",".join("[" + ",".join(cell(x) for x in s) + "]" for s in segs)
        lines.append(f'    ["{label}", [{seg_txt}]],')
    return "\n".join(lines)


def main():
    nt, ps, pr = nt_plan(), psalm_plan(), prov_plan()
    lens = [sum(z - a + 1 for _, _, a, z in segs) for _, segs in nt]
    print(f"# NT: {len(nt)} days, verses/day min {min(lens)} max {max(lens)} mean {sum(lens)/len(lens):.1f}", file=sys.stderr)

    want_js = "--py" not in sys.argv
    want_py = "--js" not in sys.argv
    header = "Generated by tools/gen_daily_plan.py — do not edit by hand."
    fmt_note = "[label, [[bookId, chapter, fromVerse, toVerse], ...]]"
    if want_js:
        print(f"// {header}\n// {fmt_note}; null verses = whole chapter")
        print("const DAILY_NT_PLAN = [\n" + fmt(nt, False) + "\n];")
        print("const DAILY_PSALM_PLAN = [\n" + fmt(ps, False) + "\n];")
        print("const DAILY_PROV_PLAN = [\n" + fmt(pr, False) + "\n];")
    if want_py:
        if want_js:
            print("\n\n")
        print(f"# {header}\n# {fmt_note}; None verses = whole chapter")
        print("DAILY_NT_PLAN = [\n" + fmt(nt, True) + "\n]")
        print("DAILY_PSALM_PLAN = [\n" + fmt(ps, True) + "\n]")
        print("DAILY_PROV_PLAN = [\n" + fmt(pr, True) + "\n]")


if __name__ == "__main__":
    main()
