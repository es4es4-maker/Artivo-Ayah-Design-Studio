# -*- coding: utf-8 -*-
"""
Proper Arabic text renderer for Artivo masters.
Uses HarfBuzz (uharfbuzz) for shaping/GPOS + FreeType (freetype-py) for raster.
This preserves ALL Quranic tashkeel & uthmani annotation marks exactly as the
font intends (arabic_reshaper + PIL basic layout silently dropped them).
"""
import numpy as np
import freetype
import uharfbuzz as hb
from PIL import Image

_font_cache = {}


def _get_font(path):
    key = path
    if key not in _font_cache:
        data = open(path, 'rb').read()
        _font_cache[key] = {
            'face': hb.Face(data),
            'ft': freetype.Face(path),
        }
    return _font_cache[key]


def shape_run(text, path, size):
    """Return (glyph_infos, glyph_positions) shaped by HarfBuzz for `text`.
    Positions are in integer pixels at `size` px ppem.

    Bidi note: HarfBuzz does NOT run the full Unicode bidi algorithm; with
    guess_segment_properties() it treats a mixed Arabic+digits string as one
    RTL run and visually REVERSES digit runs (١٢٩ shows as ٩٢١). When digits
    are present we convert to visual order ourselves (reverse everything,
    then re-reverse each maximal digit run) and shape that as LTR."""
    if any('0' <= c <= '9' or '\u0660' <= c <= '\u0669' or '\u06f0' <= c <= '\u06f9' for c in text):
        import re
        v = text[::-1]
        v = re.sub(r'[0-9\u0660-\u0669\u06f0-\u06f9]+', lambda m: m.group(0)[::-1], v)
        text = v
        force_dir = 'ltr'
    else:
        force_dir = None
    f = _get_font(path)
    font = hb.Font(f['face'])
    font.scale = (size, size)  # -> positions in pixels
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    if force_dir:
        buf.direction = force_dir
    hb.shape(font, buf, {})
    return buf.glyph_infos, buf.glyph_positions


def measure(text, path, size):
    """Advance width in pixels for a single-line string."""
    _, poss = shape_run(text, path, size)
    return int(sum(p.x_advance for p in poss))


def line_metrics(path, size):
    ft = _get_font(path)['ft']
    ft.set_pixel_sizes(0, size)
    asc = ft.size.ascender >> 6
    desc = -(ft.size.descender >> 6)
    return asc, desc


def render_line(text, path, size, color=(0, 0, 0)):
    """Render single line -> RGBA Image (tight, includes ascender/descender)."""
    if not text:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    infos, poss = shape_run(text, path, size)
    ft = _get_font(path)['ft']
    ft.set_pixel_sizes(0, size)
    pad = max(4, int(size * 0.45))
    total = sum(p.x_advance for p in poss)
    asc, desc = line_metrics(path, size)
    W = int(total) + 2 * pad
    H = int(asc + desc) + 2 * pad
    img = np.zeros((H, W), np.uint8)
    pen = pad
    base = pad + asc
    for g, p in zip(infos, poss):
        gid = g.codepoint
        if gid == 0:
            pen += p.x_advance
            continue
        ft.load_glyph(gid, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_RENDER)
        bm = ft.glyph.bitmap
        gl = ft.glyph
        gx = pen + gl.bitmap_left + p.x_offset
        gy = base - gl.bitmap_top - p.y_offset
        if bm.width and bm.rows:
            a = np.array(bm.buffer, dtype=np.uint8).reshape(bm.rows, bm.width)
            if bm.pitch < 0:
                a = a[::-1]
            if bm.pixel_mode != 2:  # not gray -> fallback resize
                a = a.astype(np.uint8)
            x0 = max(gx, 0); y0 = max(gy, 0)
            x1 = min(gx + bm.width, W); y1 = min(gy + bm.rows, H)
            if x1 > x0 and y1 > y0:
                sub = a[y0 - gy:y1 - gy, x0 - gx:x1 - gx]
                img[y0:y1, x0:x1] = np.maximum(img[y0:y1, x0:x1], sub)
        pen += p.x_advance
    alpha = Image.fromarray(img, 'L')
    rgb = Image.new('RGBA', (W, H), tuple(color[:3]) + (255,))
    rgb.putalpha(alpha)
    return rgb


def draw_line_centered(canvas, text, path, size, cx, y_center, color=(0, 0, 0)):
    """Alpha-composite a centered line onto an RGBA PIL `canvas` at (cx, y_center)."""
    line = render_line(text, path, size, color)
    x = int(cx - line.width / 2)
    y = int(y_center - line.height / 2)
    canvas.alpha_composite(line, (int(x), int(y)))
    return line.width, line.height
