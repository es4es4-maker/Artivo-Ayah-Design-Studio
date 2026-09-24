#!/usr/bin/env python3
"""Build 300 print masters (60x80cm @300DPI) + proof thumbs + zips from 10 approved plates x 30 verified verses."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from artivo_text import measure, draw_line_centered, line_metrics  # HarfBuzz shaping: full tashkeel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATES = f'{ROOT}/deliverables/plates'
OUT = f'{ROOT}/deliverables/masters'
PROOFS = f'{ROOT}/proofs'          # gitignored — proofs must never land in git
FONT = f'{ROOT}/assets/fonts/NotoNaskhArabic-Regular.ttf'
os.makedirs(OUT, exist_ok=True); os.makedirs(PROOFS, exist_ok=True)

VERSES = json.load(open(f'{ROOT}/assets/verses.json'))
ALL_A = [v for v in VERSES if v['key'].startswith('A')]
MAIN300 = [v for v in ALL_A if 1 <= int(v['key'][1:]) <= 300]
assert len(MAIN300) == 300 and len({v['ref'] for v in ALL_A}) == len(ALL_A), 'need 300 unique verses'

def plate_verses(pid):
    """Thirty distinct verses assigned to plate `pid` (1-based)."""
    return MAIN300[pid-1::10]

SEPIA = (120, 74, 30)
GOLD = (240, 214, 140)
# plate layout: (fx0, fx1, fy0, fy1, ink)
CFG = {
 1:(0.12,0.88, 0.22,0.58, SEPIA),   # sepia mosque portrait (clear band: pendant end at 0.21 to above domes at 0.60)
 2:(0.10,0.90, 0.40,0.76, GOLD),    # navy portrait, medallion top
 3:(0.44,0.93, 0.22,0.78, SEPIA),   # cream left vine
 4:(0.12,0.88, 0.34,0.63, GOLD),    # navy, medallion bottom, fleuron top (tip at 0.33 cleared)
 5:(0.18,0.82, 0.33,0.76, SEPIA),   # mughal arch (inside arch opening)
 6:(0.08,0.92, 0.40,0.72, GOLD),    # navy rich, medallion top, rhombus bottom
 7:(0.13,0.87, 0.46,0.80, GOLD),    # charcoal landscape (clear of side flourishes & ring)
 8:(0.12,0.88, 0.32,0.72, SEPIA),   # cream double flourish
 9:(0.10,0.90, 0.46,0.80, SEPIA),   # cream landscape, ring top
 10:(0.08,0.92, 0.26,0.82, GOLD),   # navy landscape palmette
}
DPI300_W, DPI300_H = 7087, 9449  # 60x80cm

# Measured SAFE text bands (top,bottom) for plates with near-text ornaments.
# The block is centered inside the band and the font shrinks until the EXACT
# blit box of every rendered line (same extents draw_line_centered() will
# paint, padding included) lies fully inside the band. If 12 shrink attempts
# still fail, the build prints a loud LAYOUT warning and exits non-zero.
SAFE_BAND = {
 1:(0.225, 0.575),   # below pendant (0.21) to above central dome tip
 4:(0.345, 0.625),
 5:(0.345, 0.740),
 7:(0.47,  0.795),
}


def _line_box(text, size, cx, y_center):
    """Exact pixel box draw_line_centered() blits for `text` (render_line image extents)."""
    pad = max(4, int(size * 0.45))
    asc, desc = line_metrics(FONT, size)
    w = int(measure(text, FONT, size)) + 2 * pad
    h = int(asc + desc) + 2 * pad
    x0 = int(cx - w / 2)
    y0 = int(y_center - h / 2)
    return (x0, y0, x0 + w, y0 + h)


def _layout_boxes(vtext, caption, plate_id, W, H, zcx, iw, ih, fs_override=None):
    """Return (lines, fs, boxes, y0). boxes=(x0,y0,x1,y1) = exact blit boxes."""
    fx0, fx1, fy0, fy1, ink = CFG[plate_id]
    fs_cap = fs_override if fs_override else int(ih/5.2)
    lines, fs = fit_layout(vtext, int(iw*0.96), int(ih*0.90), fs_cap)
    cap_fs = int(fs*0.42)
    vh = int(len(lines)*fs*1.52) + cap_fs*2
    if plate_id in SAFE_BAND:
        st, sb = SAFE_BAND[plate_id]
        cy = (st+sb)/2*H
    else:
        cy = (fy0+fy1)/2*H
    y0 = int(cy) - vh//2
    boxes = []
    y = y0
    for ln in lines:
        boxes.append(_line_box(ln, fs, zcx, y + fs // 2))
        y += int(fs*1.52)
    boxes.append(_line_box(caption, cap_fs, zcx, y + int(fs*0.30)))
    return lines, fs, boxes, y0

def fit_layout(text, iw, ih, fontsize_cap):
    """Return (wordsplit_lines, fontsize) that fits zone iw x ih."""
    words = text.split()
    def wrap(fs):
        lines, cur = [], []
        for w in words:
            test = ' '.join(cur + [w])
            if measure(test, FONT, fs) <= iw or not cur:
                cur.append(w)
            else:
                lines.append(' '.join(cur)); cur = [w]
        if cur: lines.append(' '.join(cur))
        return lines
    fs = fontsize_cap
    while fs > 12:
        lines = wrap(fs)
        if len(lines) * fs * 1.52 <= ih and len(lines) <= 6:
            return lines, fs
        fs -= max(2, int(fs*0.04))
    return wrap(fs), fs

def build(plate_id, verse, out_path, proof_path=None):
    p = Image.open(f'{PLATES}/plate_R{plate_id}.jpg').convert('RGB')
    landscape = p.width > p.height
    T = (DPI300_W, DPI300_H) if not landscape else (DPI300_H, DPI300_W)
    bg = p.resize(T, Image.Resampling.LANCZOS).filter(ImageFilter.UnsharpMask(radius=3, percent=70, threshold=2))
    W, H = T
    fx0, fx1, fy0, fy1, ink = CFG[plate_id]
    zcx = int((fx0 + fx1) / 2 * W)
    iw = int((fx1 - fx0) * W)
    ih = int((fy1 - fy0) * H)
    warn = None
    # Safe-band enforcement (plates with near-by ornaments):
    # shrink font until every blit box clears the measured safe band.
    if plate_id in SAFE_BAND:
        st, sb = SAFE_BAND[plate_id]
        fs_cap = int(ih / 6.4)
        for _attempt in range(12):
            lines, fs, boxes, y0 = _layout_boxes(verse['text'], verse['caption'], plate_id, W, H, zcx, iw, ih, fs_cap)
            top = min(b[1] for b in boxes); bot = max(b[3] for b in boxes)
            if top >= st*H and bot <= sb*H:
                break
            fs_cap = int(fs_cap * 0.93)
        else:
            warn = (f'{verse["key"]} (D{plate_id:02d}): خارج الشريط الآمن حتى بعد 12 محاولة '
                    f'(top={top / H:.3f}, bot={bot / H:.3f}, band={st}-{sb})')
            print('LAYOUT WARNING:', warn, flush=True)
    else:
        lines, fs = fit_layout(verse['text'], int(iw*0.96), int(ih*0.90), int(ih/5.2))
        cap_fs = int(fs * 0.42)
        vh = int(len(lines) * fs * 1.52) + cap_fs * 2
        y0 = int((fy0 + fy1) / 2 * H) - vh // 2
    cap_fs = int(fs * 0.42)
    ly = Image.new('RGBA', T, (0, 0, 0, 0))
    y = y0
    for ln in lines:
        draw_line_centered(ly, ln, FONT, fs, zcx, y + fs // 2, ink + (255,))
        y += int(fs * 1.52)
    draw_line_centered(ly, verse['caption'], FONT, cap_fs, zcx, y + int(fs * 0.30), ink + (255,))
    out = Image.alpha_composite(bg.convert('RGBA'), ly).convert('RGB')
    out.save(out_path, 'JPEG', quality=90, dpi=(300, 300))
    if proof_path:
        pr = out.copy(); pr.thumbnail((520, 700))
        pr.save(proof_path, quality=93)
    return out.size, fs, len(lines), warn

def _job(a):
    pid, v, o, p = a
    *_, warn = build(pid, v, o, p)
    return warn or ''

def build_full(args=None):
    from concurrent.futures import ProcessPoolExecutor
    import zipfile
    jobs=[]
    for pid in range(1,11):
        for v in plate_verses(pid):                    # 300 designs: 10 plates x 30 verses
            out=f'{OUT}/D{pid:02d}-{v["key"]}_60x80_300dpi.jpg'
            proof=f'{PROOFS}/proof_D{pid:02d}_{v["key"]}.jpg'
            jobs.append((pid,v,out,proof))
    warns=[]
    with ProcessPoolExecutor(max_workers=2) as ex:
        for i,res in enumerate(ex.map(_job,jobs)):
            if res: warns.append(res)
            if (i+1)%20==0: print(f'...{i+1}/{len(jobs)}',flush=True)
    # zips per plate: 3 parts of 10 designs each (GitHub rejects files >100MB)
    os.makedirs(f'{ROOT}/deliverables/zips',exist_ok=True)
    for pid in range(1,11):
        vs = plate_verses(pid)
        for oldp in (f'{ROOT}/deliverables/zips/Artivo_D{pid:02d}_30-designs.zip',
                     f'{ROOT}/deliverables/zips/Artivo_D{pid:02d}_10-designs.zip'):
            if os.path.exists(oldp): os.remove(oldp)
        for pi in range(3):
            z=f'{ROOT}/deliverables/zips/Artivo_D{pid:02d}_part{pi+1}.zip'
            with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zz:
                for v in vs[pi*10:(pi+1)*10]:
                    zz.write(f'{OUT}/D{pid:02d}-{v["key"]}_60x80_300dpi.jpg',f'Artivo_D{pid:02d}-{v["key"]}_60x80cm_300DPI.jpg')
            print('zip',pid,'part',pi+1,os.path.getsize(z)//1_000_000,'MB',flush=True)
    if warns:
        print(f'\nLAYOUT WARNINGS: {len(warns)} تصميم لم يستقر داخل الشريط الآمن', flush=True)
        for w in warns:
            print('  -', w, flush=True)
    print('FULL BUILD DONE' if not warns else 'FULL BUILD DONE (مع تحذيرات تخطيط)', flush=True)
    return 1 if warns else 0

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'full':
        raise SystemExit(build_full(sys.argv[2:]) or 0)
    for pid, vk in ((1, 'A001'), (7, 'A092')):
        v = next(x for x in ALL_A if x['key'] == vk)
        proto = f'{PROOFS}/_test_D{pid:02d}_{vk}.jpg'
        print(pid, vk, build(pid, v, '/tmp/_m.jpg', proto))
