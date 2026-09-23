#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify every Artivo deliverable — the "zero errors" gate.

Checks (fast → full):
  1. verses.json structure: B00 + A001..A300, unique refs, sane captions
  2. every verse text matched CHARACTER-BY-CHARACTER against the pinned
     quran-json (tanzil uthmani) source; only decorative marks (۞ U+06DE,
     small waqf U+06D6..06DC, ZWJ/NBSP, uthmani sukun) are ignorable
  3. caption = "<surah name> : <arabic-indic ayah number>" and correct
  4. zips: exact names, <100MB each, CRC-clean members, 10/100 per zip,
     masters in the right part, no duplicates
  5. masters: JPEG / RGB / 7087x9449 / 300DPI (headers; optional deep decode)
  6. mockups: one per master key, same orientation

Usage:
  python3 tools/verify_all.py            # everything found locally
  python3 tools/verify_all.py --fast     # texts + names only (CI, no big IO)
  python3 tools/verify_all.py --deep 24  # + fully decode 24 images
  python3 tools/verify_all.py --fetch-release v1.0   # pull zips from a release

Exit code 0 = zero errors (warnings allowed), 1 = at least one error.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IND = "٠١٢٣٤٥٦٧٨٩"
NAME_FIX = {14: "إبراهيم", 34: "سبأ"}  # quran-json ships these two un-hamzated
DROP = {c: None for c in (0x06DE, 0x06E9, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF)}
DROP[0x00A0] = " "
WAQF = {c: None for c in range(0x06D6, 0x06DD)}


def strict(s: str) -> str:
    return " ".join(s.translate(DROP).split())


def lenient(s: str) -> str:
    s = s.translate(DROP).translate(WAQF).replace("\u0652", "\u06E1")
    return " ".join(s.split())


def dk(k) -> str:
    return f"D{k[0]:02d}-A{k[1]:03d}"


class Report:
    def __init__(self):
        self.lines: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def section(self, t: str):
        self.lines.append(f"\n### {t}")

    def ok(self, m: str):
        self.lines.append(f"- ✅ {m}")

    def info(self, m: str):
        self.lines.append(f"- ℹ️ {m}")

    def warn(self, m: str):
        self.warnings.append(m)
        self.lines.append(f"- ⚠️ {m}")

    def err(self, m: str):
        self.errors.append(m)
        self.lines.append(f"- ❌ {m}")

    def render(self) -> str:
        verdict = "✅ صفر أخطاء" if not self.errors else f"❌ {len(self.errors)} مشكلة"
        if self.warnings:
            verdict += f" • ⚠️ {len(self.warnings)} ملاحظة للمراجعة"
        return (f"## تقرير الفحص الآلي: ستوديو آرتيفو\n\nالنتيجة: **{verdict}**\n"
                + "\n".join(self.lines) + "\n")


# ---------------------------------------------------------------- sources
def load_reference():
    """({(sura, ayah): text}, names, label) from the pinned quran-json."""
    local = ROOT / "tools" / "node_modules" / "quran-json" / "dist" / "quran.json"
    if local.exists():
        q = json.loads(local.read_text(encoding="utf-8"))
        label = "tools/node_modules/quran-json (npm ci)"
    else:
        lock = json.loads((ROOT / "tools" / "package-lock.json").read_text(encoding="utf-8"))
        meta = lock["packages"]["node_modules/quran-json"]
        data = urllib.request.urlopen(meta["resolved"], timeout=120).read()
        algo, want = meta["integrity"].split("-", 1)
        got = base64.b64encode(hashlib.new(algo, data).digest()).decode()
        if got != want:
            raise RuntimeError("بصمة quran-json غير مطابقة لـ package-lock.json")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            q = json.load(tf.extractfile("package/dist/quran.json"))
        label = f"quran-json@{meta['version']} (npm tarball, integrity {algo} ✓)"
    src = {(c["id"], v["id"]): v["text"] for c in q for v in c["verses"]}
    names = {c["id"]: c["name"] for c in q}
    return src, names, label


def fetch_release_zips(tag: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/es4es4-maker/Artivo-Ayah-Design-Studio/releases/download/{tag}/"
    names = ([f"Artivo_D{p:02d}_part{i}.zip" for p in range(1, 11) for i in (1, 2, 3)]
             + [f"Artivo_Mockups_Golden-Frame_part{i}.zip" for i in (1, 2, 3)])
    for n in names:
        out = dest / n
        if not out.exists():
            print(f"  ↓ {n}", flush=True)
            urllib.request.urlretrieve(base + n, out)
    return dest


# ---------------------------------------------------------------- checks
def check_texts(r: Report):
    r.section("البنية والنصوص (حرف-بحرف ضد tanzil)")
    verses = json.loads((ROOT / "assets" / "verses.json").read_text(encoding="utf-8"))
    by_key = {}
    for v in verses:
        if v["key"] in by_key:
            r.err(f"verses.json: مفتاح مكرر {v['key']}")
        by_key[v["key"]] = v
    keys = [f"A{i:03d}" for i in range(1, 301)]
    missing = [k for k in keys if k not in by_key]
    if missing:
        r.err(f"verses.json: مفاتيح ناقصة ({len(missing)}): " + ", ".join(missing[:20]))
    else:
        r.ok("verses.json: B00 + A001..A300 موجودة")
    dup = sorted(x for x, c in Counter(by_key[k]["ref"] for k in keys if k in by_key).items() if c > 1)
    if dup:
        r.err("مراجع متكررة: " + ", ".join(dup))
    else:
        r.ok("300 مرجع فريد — صفر تكرار")

    try:
        src, names, label = load_reference()
    except Exception as e:
        r.err(f"تعذر تحميل مصدر quran-json: {e}")
        return
    r.info(f"المصدر: {label}")

    exact = soft = partial = 0
    softs, partials = [], []
    checked = (["B00"] if "B00" in by_key else []) + [k for k in keys if k in by_key]
    for k in checked:
        v = by_key[k]
        report = r.warn if k == "B00" else r.err  # B00 badge: not on any master
        try:
            s, a = (int(x) for x in v["ref"].split(":"))
            ref_text = src[(s, a)]
        except Exception:
            report(f"{k}: مرجع غير صالح أو غير موجود «{v.get('ref')}»")
            continue
        t = v.get("text", "")
        if strict(t) == strict(ref_text):
            exact += 1
        elif lenient(t) == lenient(ref_text):
            soft += 1
            softs.append(k)
        elif lenient(t) and f" {lenient(t)} " in f" {lenient(ref_text)} ":
            partial += 1
            partials.append(k)
        else:
            tw, sw = lenient(t).split(), lenient(ref_text).split()
            i = next((j for j in range(min(len(tw), len(sw))) if tw[j] != sw[j]), min(len(tw), len(sw)))
            report(f"{k} ({v['ref']}): اختلاف من الكلمة {i + 1}: «{' '.join(tw[i:i+3])}» ≠ «{' '.join(sw[i:i+3])}»")
        cap = v.get("caption", "").translate(DROP).strip()
        m = re.fullmatch(r"(.+?)\s*:\s*([٠-٩]+)", cap)
        num = "".join(IND[int(d)] for d in str(a))
        name = NAME_FIX.get(s, names.get(s, "?"))
        if not m:
            report(f"{k}: صيغة المرجع المكتوب غير متوقعة «{cap}»")
        elif m[2] != num:
            report(f"{k}: رقم الآية المكتوب «{m[2]}» والصحيح «{num}» ({v['ref']})")
        elif m[1] != name:
            r.warn(f"{k}: اسم السورة «{m[1]}» والمتوقع «{name}» (للمراجعة)")
    r.ok(f"{exact} نص مطابق 100% حرف-بحرف (تجاهل ۞ فقط)")
    if soft:
        r.info(f"{soft} نص مطابق بعد تجاهل علامات الوقف الصغيرة/السكون: " + ", ".join(softs))
    if partial:
        r.info(f"{partial} نص جزء متصل من الآية وليس الآية كاملة: " + ", ".join(partials))
    if not r.errors:
        r.ok(f"الـ{len(checked)} نص كلهم سليمين وأرقام الآيات في المراجع كلها صح")


def check_zips(r: Report, zdir: Path, deep: int):
    r.section("الزيبات (الأسماء والحجم وCRC)")
    have = sorted(p.name for p in zdir.glob("*.zip"))
    want = [f"Artivo_D{p:02d}_part{i}.zip" for p in range(1, 11) for i in (1, 2, 3)]
    want += [f"Artivo_Mockups_Golden-Frame_part{i}.zip" for i in (1, 2, 3)]
    missing = [w for w in want if w not in have]
    extra = [h for h in have if h not in want]
    if missing:
        r.err(f"زيبات ناقصة ({len(missing)}): " + ", ".join(missing))
    if extra:
        r.warn("زيبات غير متوقعة: " + ", ".join(extra))
    big = [n for n in have if (zdir / n).stat().st_size >= 100 * 1024 * 1024]
    if big:
        r.err("أحجام ≥ 100MB: " + ", ".join(big))
    if not missing and not big:
        r.ok(f"{len(have)} زيب بالأسماء المتوقعة وكلها < 100MB")

    masters: dict = {}
    mockups: dict = {}
    for zn in have:
        zp = zdir / zn
        is_mock = zn.startswith("Artivo_Mockups")
        try:
            with zipfile.ZipFile(zp) as zf:
                entries = [i for i in zf.infolist() if not i.is_dir()]
                bad = zf.testzip()
                if bad:
                    r.err(f"{zn}: CRC فشل في {bad}")
                for e in entries:
                    base = os.path.basename(e.filename)
                    m = (re.search(r"D(\d{2})-A(\d{3})", base) if is_mock
                         else re.fullmatch(r"Artivo_D(\d{2})-A(\d{3})_60x80cm_300DPI\.jpg", base))
                    if not m:
                        r.err(f"{zn}: اسم عضو غير متوقع «{e.filename}»")
                        continue
                    key = (int(m[1]), int(m[2]))
                    table = mockups if is_mock else masters
                    if key in table:
                        r.err(f"{dk(key)}: مكرر في {table[key][0]} و {zn}")
                    table[key] = (zn, e.file_size, e.filename)
                want_n = 100 if is_mock else 10
                if len(entries) != want_n:
                    r.err(f"{zn}: فيه {len(entries)} عضو بدل {want_n}")
        except zipfile.BadZipFile as ex:
            r.err(f"{zn}: زيب تالف ({ex})")

    if not any(("CRC" in e or "تالف" in e) for e in r.errors):
        r.ok("كل الأعضاء داخل الـ33 زيب نجحوا في فحص CRC")

    expect = {(p, k) for p in range(1, 11) for k in range(p, 301, 10)}
    for label, table in (("ماسترز", masters), ("موك-أب", mockups)):
        miss, extra_k = expect - set(table), set(table) - expect
        if miss:
            r.err(f"{label} ناقصة من الزيبات ({len(miss)}): " + ", ".join(map(dk, sorted(miss)[:15])))
        if extra_k:
            r.err(f"{label} بمفاتيح غير متوقعة: " + ", ".join(map(dk, sorted(extra_k)[:15])))
    if set(masters) == expect:
        r.ok("300 ماستر داخل الزيبات (10 خلفيات × 30 بمفاتيح مكتملة)")
    if set(mockups) == expect:
        r.ok("300 موك-أب داخل الزيبات (واحد لكل ماستر)")

    bad_place = []
    for (p, k), (zn, _, _) in masters.items():
        part = ((k - p) // 10) // 10 + 1
        if zn != f"Artivo_D{p:02d}_part{part}.zip":
            bad_place.append(dk((p, k)))
    if bad_place:
        r.err(f"{len(bad_place)} ماستر في زيب جزء غلط (مثال: " + ", ".join(bad_place[:10]) + ")")
    elif masters:
        r.ok("توزيع الأجزاء: كل ماستر في الجزء الصحيح (10 تصميمات لكل جزء)")

    if deep > 0:
        r.section(f"فك ترميز كامل لـ{deep} صورة (كشف القطع/التلف)")
        try:
            from PIL import Image
        except ImportError:
            r.warn("Pillow مش متثبت — اتخطى فك الترميز (pip install pillow)")
            return
        n = 0
        for zn, _, member in list(masters.values())[:: max(1, len(masters) // max(1, deep * 2 // 3))][: max(1, deep * 2 // 3)]:
            with zipfile.ZipFile(zdir / zn) as zf:
                Image.open(io.BytesIO(zf.read(member))).load()
            n += 1
        for zn, _, member in list(mockups.values())[:: max(1, len(mockups) // max(1, deep // 3 or 1))][: max(1, deep // 3)]:
            with zipfile.ZipFile(zdir / zn) as zf:
                Image.open(io.BytesIO(zf.read(member))).load()
            n += 1
        r.ok(f"{n} صورة اتفك ترميزها بالكامل بنجاح")


def check_images(r: Report, zdir: Path):
    r.section("الصور (JPEG/RGB/7087×9449/300DPI + اتجاهات)")
    try:
        from PIL import Image
    except ImportError:
        r.warn("Pillow مش متثبت — اتخطى فحص الصور (pip install pillow)")
        return
    masters, mockups = {}, {}
    for zname in sorted(p.name for p in zdir.glob("*.zip")):
        is_mock = zname.startswith("Artivo_Mockups")
        table = mockups if is_mock else masters
        with zipfile.ZipFile(zdir / zname) as zf:
            for e in zf.infolist():
                if e.is_dir():
                    continue
                base = os.path.basename(e.filename)
                m = (re.search(r"D(\d{2})-A(\d{3})", base) if is_mock
                     else re.fullmatch(r"Artivo_D(\d{2})-A(\d{3})_60x80cm_300DPI\.jpg", base))
                if not m:
                    continue
                key = (int(m[1]), int(m[2]))
                with zf.open(e) as fh:
                    head = fh.read(96 * 1024)
                try:
                    im = Image.open(io.BytesIO(head))
                    dpi = im.info.get("dpi")
                    table[key] = (im.format, im.size, im.mode,
                                  tuple(round(float(x)) for x in dpi) if dpi else None, base)
                except Exception:
                    with zf.open(e) as fh:
                        data = fh.read()
                    try:
                        im = Image.open(io.BytesIO(data))
                        dpi = im.info.get("dpi")
                        table[key] = (im.format, im.size, im.mode,
                                      tuple(round(float(x)) for x in dpi) if dpi else None, base)
                    except Exception as ex:
                        r.err(f"{base}: صورة تالفة ({ex})")

    problems, orient = Counter(), {}
    for key, (fmt, size, mode, dpi, base) in masters.items():
        orient[key] = "L" if size[0] > size[1] else "P"
        for field, val, good in (
            ("الصيغة", fmt, fmt == "JPEG"),
            ("الأبعاد", f"{size[0]}x{size[1]}", sorted(size) == [7087, 9449]),
            ("الوضع اللوني", mode, mode == "RGB"),
            ("DPI", str(dpi), dpi == (300, 300)),
        ):
            if not good:
                problems[f"{field}={val}"] += 1
    if problems:
        for pb, n in problems.items():
            r.err(f"{n} ماستر بـ {pb}")
    else:
        r.ok(f"{len(masters)} ماستر: JPEG • RGB • 7087×9449 • 300DPI")
    land = sorted({k[0] for k, o in orient.items() if o == "L"})
    if orient:
        r.info("الخلفيات بالعرض: " + (", ".join(f"D{p:02d}" for p in land) or "—")
               + f" ({30 * len(land)} تصميم) والباقي بالطول ({300 - 30 * len(land)} تصميم)")
    for p in range(1, 11):
        if len({o for k, o in orient.items() if k[0] == p}) > 1:
            r.err(f"D{p:02d}: اتجاهات مختلطة داخل نفس الخلفية")

    mis, sizes = [], Counter()
    for key, (fmt, size, mode, dpi, base) in mockups.items():
        sizes[f"{size[0]}x{size[1]}"] += 1
        o = "L" if size[0] > size[1] else "P"
        if key in orient and orient[key] != o:
            mis.append(dk(key))
    if mis:
        r.err(f"موك-أبس اتجاهها عكس الماستر ({len(mis)}): " + ", ".join(mis[:15]))
    else:
        r.ok(f"{len(mockups)} موك-أب: الاتجاه مطابق للماستر في كل الحالات")
    odd = {s: n for s, n in sizes.items() if s not in ("1500x2000", "2000x1500")}
    if odd:
        r.warn(f"أبعاد موك-أبس غير معتادة: {odd}")


def check_loose(r: Report, fast: bool):
    r.section("المجلدات المحلية (تقاطع مع الزيبات)")
    for sub, pat in (("masters", r"D(\d{2})-A(\d{3})_60x80_300dpi\.jpg"),
                     ("mockups", r"D(\d{2})-A(\d{3})_mockup\.jpg")):
        d = ROOT / "deliverables" / sub
        files = sorted(p.name for p in d.glob("*.jpg")) if d.is_dir() else []
        if not files:
            r.info(f"deliverables/{sub}/ غير موجود محليًا (سليم بعد التخفيف)")
            continue
        keys, bad = set(), 0
        for n in files:
            m = re.fullmatch(pat, n)
            if not m:
                bad += 1
                continue
            keys.add((int(m[1]), int(m[2])))
        expect = {(p, k) for p in range(1, 11) for k in range(p, 301, 10)}
        if bad:
            r.err(f"deliverables/{sub}/: {bad} اسم غير متوقع")
        if keys != expect:
            r.err(f"deliverables/{sub}/: ناقص {len(expect - keys)} زائد {len(keys - expect)}")
        else:
            r.ok(f"deliverables/{sub}/: 300 ملف بالمفاتيح الكاملة")
        if not fast and sub == "masters":
            try:
                from PIL import Image
                sample = files[:: max(1, len(files) // 12)][:12]
                for n in sample:
                    Image.open(d / n).load()
                r.ok(f"فك ترميز كامل لـ{len(sample)} ماستر من القرص")
            except ImportError:
                pass
            except Exception as ex:
                r.err(f"ماستر تالف على القرص: {ex}")


def main():
    ap = argparse.ArgumentParser(description="Artivo zero-error verifier")
    ap.add_argument("--fast", action="store_true", help="نصوص وأسماء فقط (للـCI)")
    ap.add_argument("--deep", type=int, default=12, metavar="N", help="فك ترميز N صورة (0=بدون)")
    ap.add_argument("--fetch-release", metavar="TAG", help="حمّل زيبات الريلايز TAG قبل الفحص")
    ap.add_argument("--zips", metavar="DIR", help="مجلد زيبات بديل")
    a = ap.parse_args()

    r = Report()
    check_texts(r)

    zdir = Path(a.zips) if a.zips else ROOT / "deliverables" / "zips"
    if a.fetch_release:
        r.info(f"تنزيل زيبات release {a.fetch_release} ...")
        zdir = fetch_release_zips(a.fetch_release, ROOT / ".cache" / "release-zips")
    if zdir.is_dir() and any(zdir.glob("*.zip")):
        if a.fast:
            r.section("الزيبات (أسماء فقط)")
            have = sorted(p.name for p in zdir.glob("*.zip"))
            want = [f"Artivo_D{p:02d}_part{i}.zip" for p in range(1, 11) for i in (1, 2, 3)]
            want += [f"Artivo_Mockups_Golden-Frame_part{i}.zip" for i in (1, 2, 3)]
            missing = [w for w in want if w not in have]
            if missing:
                r.err("زيبات ناقصة: " + ", ".join(missing))
            else:
                r.ok(f"{len(have)} زيب بالأسماء المتوقعة")
        else:
            check_zips(r, zdir, a.deep)
            check_images(r, zdir)
    else:
        r.warn(f"مفيش زيبات في {zdir} — استخدم --fetch-release v1.0 أو خلي الزيبات في deliverables/zips/")
    check_loose(r, a.fast)

    report = r.render()
    out = ROOT / "verify_report.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"(التقرير محفوظ في {out})")
    return 1 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main())
