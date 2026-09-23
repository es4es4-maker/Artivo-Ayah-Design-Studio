#!/usr/bin/env python3
"""Build 100 print masters (60x80cm @300DPI) + previews from 10 approved plates x 10 verified verses."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from artivo_text import measure, draw_line_centered  # HarfBuzz shaping: full tashkeel

ROOT = '/home/user/Artivo-Ayah-Design-Studio'
PLATES = f'{ROOT}/deliverables/plates'
OUT = f'{ROOT}/deliverables/masters'
PREV = f'{ROOT}/previews'
FONT = f'{ROOT}/assets/fonts/NotoNaskhArabic-Regular.ttf'
os.makedirs(OUT, exist_ok=True); os.makedirs(PREV, exist_ok=True)

VERSES = json.load(open(f'{ROOT}/assets/verses.json'))
ALL_A = [v for v in VERSES if v['key'].startswith('A')]
VERSES10 = ALL_A  # legacy alias
MAIN100 = [v for v in ALL_A if 1 <= int(v['key'][1:]) <= 300]
EXTRAS = [v for v in ALL_A if int(v['key'][1:]) >= 301]
assert len(MAIN100) >= 300 and len({v['ref'] for v in ALL_A}) == len(ALL_A), 'need unique verses'

def plate_verses(pid):
    """Thirty distinct verses assigned to plate `pid` (1-based)."""
    return MAIN100[pid-1::10]

def plate_extra(pid):
    """Legacy helper (unused)."""
    return [v for v in EXTRAS if int(v['key'][1:]) - 300 == pid]

SEPIA = (120, 74, 30)
GOLD = (240, 214, 140)
# plate layout: (fx0, fx1, fy0, fy1, ink)
CFG = {
 1:(0.13,0.87, 0.22,0.47, SEPIA),   # sepia mosque portrait (clear band 0.225 pendant - 0.473 minaret)
 2:(0.10,0.90, 0.40,0.70, GOLD),    # navy portrait, medallion top
 3:(0.44,0.93, 0.24,0.78, SEPIA),   # cream left vine
 4:(0.12,0.88, 0.34,0.61, GOLD),    # navy, medallion bottom, fleuron top (tip at 0.33 cleared)
 5:(0.19,0.81, 0.33,0.75, SEPIA),   # mughal arch (below arch inner curve, inside opening)
 6:(0.08,0.92, 0.40,0.68, GOLD),    # navy rich, medallion top, rhombus bottom
 7:(0.15,0.85, 0.46,0.80, GOLD),    # charcoal landscape (clear of side flourishes & ring)
 8:(0.12,0.88, 0.32,0.70, SEPIA),   # cream double flourish
 9:(0.10,0.90, 0.46,0.80, SEPIA),   # cream landscape, ring top
 10:(0.08,0.92, 0.28,0.83, GOLD),   # navy landscape palmette
}
DPI300_W, DPI300_H = 7087, 9449  # 60x80cm

# Measured SAFE text bands (top,bottom) for plates with near-text ornaments.
# Block is centered inside the band and font shrinks until the analytic ink
# bounding box (ascenders/descenders included) lies fully inside the band.
SAFE_BAND = {1:(0.245,0.455), 4:(0.345,0.605), 5:(0.345,0.725), 7:(0.47,0.81)}
from artivo_text import line_metrics

def _layout_boxes(vtext, caption, plate_id, W, H, zcx, iw, ih, fs_override=None):
    """Return (lines, fs, boxes, y0). boxes=(x0,y0,x1,y1) pixel boxes incl. asc/desc."""
    fx0, fx1, fy0, fy1, ink = CFG[plate_id]
    fs_cap = fs_override if fs_override else int(ih/6.4)
    lines, fs = fit_layout(vtext, int(iw*0.94), int(ih*0.72), fs_cap)
    cap_fs = int(fs*0.42)
    asc, desc = line_metrics(FONT, fs)
    asc_c, desc_c = line_metrics(FONT, cap_fs)
    vh = int(len(lines)*fs*1.52) + cap_fs*2
    if plate_id in SAFE_BAND:
        st, sb = SAFE_BAND[plate_id]
        cy = (st+sb)/2*H
    else:
        cy = (fy0+fy1)/2*H
    y0 = int(cy) - vh//2
    boxes = []
    y = y0
    from artivo_text import measure as _measure
    for ln in lines:
        w = _measure(ln, FONT, fs)
        boxes.append((int(zcx-w/2), y+int(fs/2)-asc, int(zcx+w/2), y+int(fs/2)+desc))
        y += int(fs*1.52)
    cw = _measure(caption, FONT, cap_fs)
    boxes.append((int(zcx-cw/2), y+int(fs*0.30)-asc_c, int(zcx+cw/2), y+int(fs*0.30)+desc_c))
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
    # Safe-band enforcement (plates with near-by ornaments):
    # shrink font until the analytic ink bounding box clears the band.
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
        lines, fs = fit_layout(verse['text'], int(iw*0.94), int(ih*0.72), int(ih/6.4))
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
    return out.size, fs, len(lines)

def _job(a):
    pid,v,o,p=a
    build(pid,v,o,p)
    return f'D{pid:02d}-{v["key"]}: OK'

def build_full(args=None):
    from concurrent.futures import ProcessPoolExecutor
    import zipfile, shutil
    jobs=[]
    for pid in range(1,11):
        for v in plate_verses(pid):                    # 300 designs: 10 plates x 30 verses
            out=f'{OUT}/D{pid:02d}-{v["key"]}_60x80_300dpi.jpg'
            proof=f'{PREV}/proof_D{pid:02d}_{v["key"]}.jpg'
            jobs.append((pid,v,out,proof))
    with ProcessPoolExecutor(max_workers=2) as ex:
        for i,res in enumerate(ex.map(_job,jobs)):
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
    print('FULL BUILD DONE',flush=True)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'full':
        build_full(sys.argv[2:])
        raise SystemExit(0)
    for pid, vk in ((1, 'A001'), (7, 'A092')):
        v = next(x for x in ALL_A if x['key'] == vk)
        proto = f'{PREV}/_test_D{pid:02d}_{vk}.jpg'
        print(pid, vk, build(pid, v, '/tmp/_m.jpg', proto))
