#!/usr/bin/env python3
"""Rebuild all mockups in the newly-approved style: slim modern gold frame on a light wall.

Commands:
  python3 tools/build_mockups_lite.py               # 300 mockups + 3 mockup zips
  python3 tools/build_mockups_lite.py mockups       # only the 300 mockups
  python3 tools/build_mockups_lite.py zips          # only Artivo_Mockups_Golden-Frame_part1..3.zip
  python3 tools/build_mockups_lite.py fetch-masters # download master zips from the release + extract

Zips are packed 100 mockups per part in sorted-filename order (the same split
the shipped release uses). fetch-masters uses $ARTIVO_RELEASE_TAG (default v1.0).
"""
import os
import sys
import urllib.request
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTERS = os.path.join(ROOT, 'deliverables/masters')
OUT = os.path.join(ROOT, 'deliverables/mockups')
ZDIR = os.path.join(ROOT, 'deliverables/zips')
os.makedirs(OUT, exist_ok=True)

RELEASE_TAG = os.environ.get('ARTIVO_RELEASE_TAG', 'v1.0')
RELEASE_BASE = f'https://github.com/es4es4-maker/Artivo-Ayah-Design-Studio/releases/download/{RELEASE_TAG}'

def wall(w, h):
    """light warm wall with soft vignette + fine grain"""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w/2, h*0.42
    d = np.sqrt(((x-cx)/(w*0.75))**2 + ((y-cy)/(h*0.75))**2)
    base = 248 - 26*np.clip(d, 0, 1)          # 248 -> 222
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1.6, (h, w))
    g = (base + noise).astype(np.float32)
    img = np.dstack([g, g*0.965, g*0.925])      # warm
    return np.clip(img, 0, 255).astype(np.uint8)

def gold_strip(w, t):
    """horizontal gold strip w x t with metallic gradient"""
    y, x = np.mgrid[0:t, 0:w].astype(np.float32)
    s = np.sin(np.pi*np.clip(y/t, 0, 1))       # 0->1->0 vertical sheen
    sweep = 0.85 + 0.15*np.cos(2*np.pi*(x/w) - 0.7)  # gentle left-right sheen
    def ch(a,b): return (a+(b-a)*s)*sweep
    r = ch(138, 224); g = ch(96, 176); b = ch(20, 74)
    return np.dstack([np.clip(r,0,239), np.clip(g,0,205), np.clip(b,0,110)]).astype(np.uint8)

def make_frame(inner_w, inner_h, t, outdir='/tmp'):
    """returns RGBA frame ring image sized (inner_w+2t, inner_h+2t)"""
    Wf, Hf = inner_w+2*t, inner_h+2*t
    img = np.zeros((Hf, Wf, 4), np.uint8)
    hz = gold_strip(Wf, t)          # horizontal strips
    img[:t, :, :3] = hz; img[-t:, :, :3] = hz
    vt = cv2.rotate(gold_strip(Hf, t), cv2.ROTATE_90_CLOCKWISE)
    img[:, :t, :3] = vt; img[:, -t:, :3] = vt
    img[..., 3] = 255
    img[2:t-2, 2:t-2] = 0; img[2:t-2, -t+2:-2] = 0
    img[2:t-2, t-2:-t+2] = 0; img[-t+2:-2, 2:-2] = 0
    # bevel lines
    p = Image.fromarray(img); d = ImageDraw.Draw(p)
    d.rectangle([t, t, Wf-t-1, Hf-t-1], outline=(250, 236, 190, 255), width=2)   # inner light lip
    d.rectangle([0, 0, Wf-1, Hf-1], outline=(120, 84, 14, 255), width=1)        # outer dark edge
    return p

def mockup(master_path, out_path):
    art0 = Image.open(master_path).convert('RGB')
    landscape = art0.width > art0.height
    cw, ch = (2000, 1500) if landscape else (1500, 2000)
    img = Image.fromarray(wall(cw, ch))
    # inner art box: landscape ~ art aspect 1.33 ; portrait 0.75
    if landscape:
        aw = int(cw*0.70); ah = int(aw*art0.height/art0.width)
    else:
        ah = int(ch*0.74); aw = int(ah*art0.width/art0.height)
    t = max(14, int(cw*0.011))
    fw, fh = aw+2*t, ah+2*t
    fx, fy = (cw-fw)//2, int((ch-fh)*0.44)
    # wall shadow under frame (soft, slightly down-right)
    sh = Image.new('RGBA', (cw, ch), (0,0,0,0))
    ImageDraw.Draw(sh).rectangle([fx+18, fy+26, fx+18+fw, fy+26+fh], fill=(40,30,18,110))
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    img = Image.alpha_composite(img.convert('RGBA'), sh)
    # frame
    ring = make_frame(aw, ah, t)
    img.paste(ring, (fx, fy), ring)
    # thin inner shadow line above art
    art = art0.resize((aw, ah), Image.Resampling.LANCZOS)
    img.paste(art, (fx+t, fy+t))
    d = ImageDraw.Draw(img)
    d.rectangle([fx+t, fy+t, fx+t+aw-1, fy+t+ah-1], outline=(70, 50, 12, 255), width=2)
    # faint top-sheen on the frame corners (tiny bright ticks)
    img.convert('RGB').save(out_path, quality=92)

def build_mockups():
    names = sorted(f for f in os.listdir(MASTERS) if f.endswith('.jpg'))
    if not names:
        raise SystemExit(f'{MASTERS} فاضي — نفّذ fetch-masters الأول')
    for n in names:
        key = n.split('_60x80')[0]
        out = os.path.join(OUT, f'{key}_mockup.jpg')
        mockup(os.path.join(MASTERS, n), out)
    print('mockups done', len(names))

def build_mockup_zips():
    """Artivo_Mockups_Golden-Frame_part1..3.zip — 100 mockups per part."""
    names = sorted(f for f in os.listdir(OUT) if f.endswith('.jpg'))
    if len(names) != 300:
        raise SystemExit(f'{OUT} فيه {len(names)} موك-أب بدل 300')
    os.makedirs(ZDIR, exist_ok=True)
    for i in range(3):
        zp = os.path.join(ZDIR, f'Artivo_Mockups_Golden-Frame_part{i+1}.zip')
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as zz:
            for n in names[i*100:(i+1)*100]:
                zz.write(os.path.join(OUT, n), n)
        print('mockup zip part', i+1, os.path.getsize(zp)//1_000_000, 'MB')

def fetch_masters():
    """Download the 30 master zips from the release and extract the 300 JPGs."""
    os.makedirs(MASTERS, exist_ok=True)
    os.makedirs(ZDIR, exist_ok=True)
    got = 0
    for p in range(1, 11):
        for part in (1, 2, 3):
            zn = f'Artivo_D{p:02d}_part{part}.zip'
            zp = os.path.join(ZDIR, zn)
            if not os.path.exists(zp):
                print('download', zn, flush=True)
                urllib.request.urlretrieve(f'{RELEASE_BASE}/{zn}', zp)
            with zipfile.ZipFile(zp) as zf:
                for member in zf.namelist():
                    base = os.path.basename(member)
                    if not base.lower().endswith('.jpg'):
                        continue
                    # Artivo_D01-A001_60x80cm_300DPI.jpg -> D01-A001_60x80_300dpi.jpg
                    disk = base.replace('Artivo_', '').replace('_60x80cm_300DPI', '_60x80_300dpi')
                    with open(os.path.join(MASTERS, disk), 'wb') as out:
                        out.write(zf.read(member))
                    got += 1
    print('masters extracted:', got)

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd in ('all', 'mockups'):
        build_mockups()
    if cmd in ('all', 'zips'):
        build_mockup_zips()
    if cmd == 'fetch-masters':
        fetch_masters()
    if cmd not in ('all', 'mockups', 'zips', 'fetch-masters'):
        raise SystemExit(__doc__)
