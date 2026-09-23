#!/usr/bin/env python3
"""Download portal + direct upload endpoint for reference images.

Hardened:
  * root = <repo>/deliverables (was a hardcoded absolute path)
  * uploads land in <repo>/var/uploads/incoming (gitignored)
  * body streamed to disk in 64KB chunks — never fully in RAM
  * caps: 25MB per request, 20MB per file (HTTP 413 beyond)
  * /status is off unless ARTIVO_STATUS_TOKEN is set in the environment
"""
import functools
import http.server
import json
import os
import re
import time
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(REPO, 'deliverables')
INCOMING = os.path.join(REPO, 'var', 'uploads', 'incoming')
os.makedirs(INCOMING, exist_ok=True)

MAX_BODY = 25 * 1024 * 1024   # one request
MAX_FILE = 20 * 1024 * 1024   # one uploaded file
CHUNK = 64 * 1024
OK_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.zip')

UPLOAD_PAGE = '''<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>رفع الصور المرجعية</title>
<style>
body{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#0d1220;color:#f0ead6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px}
.box{background:#16203a;border:1px solid #2a3a5e;border-radius:16px;padding:36px;max-width:520px;width:100%;text-align:center}
h1{color:#d4af37;font-size:1.5rem;margin-bottom:8px}
p{color:#b9b2a0;line-height:1.8;margin-bottom:20px}
input[type=file]{display:block;margin:0 auto 18px;color:#f0ead6;background:#1e2c4d;border:1px solid #3a4d7a;border-radius:10px;padding:14px;width:100%;box-sizing:border-box}
button{background:#d4af37;color:#0d1220;border:0;border-radius:10px;padding:14px 40px;font-size:1.1rem;font-weight:bold;cursor:pointer;width:100%}
button:disabled{background:#555;cursor:wait}
#st{margin-top:18px;font-size:1rem;min-height:26px}
.ok{color:#7ee08a}.bad{color:#ff9c9c}
a{color:#8fa3cf;display:inline-block;margin-top:14px}
</style></head><body><div class="box">
<h1>📤 رفع الصور المرجعية</h1>
<p>اختار الصور (ممكن أكتر من صورة)<br>واضغط <b>إرسال</b> — هتظهر رسالة «وصلت» تحت.<br>
<span style="font-size:.85rem">الحد الأقصى: ٢٠ ميجابايت للملف الواحد</span></p>
<form id="f"><input id="fi" type="file" accept="image/*,.zip" multiple required>
<button id="bt" type="submit">إرسال ⬆</button></form>
<div id="st"></div>
<a href="/">→ رجوع لصفحة التحميل</a>
<script>
const f=document.getElementById('f'),st=document.getElementById('st'),bt=document.getElementById('bt');
f.addEventListener('submit',async e=>{
 e.preventDefault();bt.disabled=true;st.className='';st.textContent='⏳ جاري الرفع...';
 try{
  const fd=new FormData();
  for(const x of document.getElementById('fi').files)fd.append('files',x,x.name);
  const r=await fetch('/upload',{method:'POST',body:fd});
  const j=await r.json();
  if(j.ok){st.className='ok';st.textContent='✅ وصلت '+j.count+' ملف(ات)! المساعد شغال عليها دلوقتي.';}
  else{st.className='bad';st.textContent='❌ '+(j.err||'خطأ');bt.disabled=false;}
 }catch(err){st.className='bad';st.textContent='❌ مشكلة اتصال — جرّب تاني.';bt.disabled=false;}
});
</script></div></body></html>'''

def sniff_ext(head, orig_ext):
    low = head[:12].lower()
    return ('.jpg' if low[:3] == b'\xff\xd8\xff' else
            '.png' if low[:8] == b'\x89PNG\r\n\x1a\n' else
            '.zip' if low[:2] == b'PK' else
            orig_ext if orig_ext in OK_EXT else '.bin')

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        if self.path.startswith('/uploader'):
            b = UPLOAD_PAGE.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path.startswith('/status'):
            secret = os.environ.get('ARTIVO_STATUS_TOKEN', '')
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not secret or q.get('token', [''])[0] != secret:
                self._j({'ok': False, 'err': 'disabled'}, 404)
                return
            fl = sorted(os.listdir(INCOMING))
            self._j({'files': fl, 'count': len(fl)})
            return
        super().do_GET()

    def do_POST(self):
        if not self.path.startswith('/upload'):
            self._j({'ok': False, 'err': 'bad path'}, 404)
            return
        try:
            ct = self.headers.get('Content-Type', '')
            m = re.search(r'boundary=(.+)$', ct)
            if not m:
                self._j({'ok': False, 'err': 'no boundary'}, 400)
                return
            boundary = m.group(1).strip().strip('"').encode()
            length = int(self.headers.get('Content-Length', 0))
            if length <= 0:
                self._j({'ok': False, 'err': 'empty body'}, 400)
                return
            if length > MAX_BODY:
                self._j({'ok': False, 'err': f'body too large (max {MAX_BODY // 2**20}MB)'}, 413)
                return
            saved = self._parse_multipart(boundary, length)
            self._j({'ok': saved > 0, 'count': saved})
        except ValueError as e:
            self._j({'ok': False, 'err': str(e)}, 413)
        except Exception as e:
            print('UPLOAD-ERR', e, flush=True)
            self._j({'ok': False, 'err': str(e)}, 500)

    # ---- streaming multipart: bounded buffers, per-part temp files --------
    def _parse_multipart(self, boundary, length):
        """Parse `length` bytes of multipart body without buffering it whole:
        the socket is read in 64KB chunks and each part is spooled to its own
        temp file while being scanned for the next boundary."""
        dash = b'--' + boundary
        marker = b'\r\n' + dash          # the delimiter as it appears between parts
        state = 'seek_first'             # seek_first | headers | body | done
        buf = b''
        got = 0
        hdr = b''
        part = None                      # current (fileobj, tmpname, size, magic)
        orig_ext = ''
        saved = 0

        def refill():
            nonlocal buf, got
            if got >= length:
                return False
            chunk = self.rfile.read(min(CHUNK, length - got))
            if not chunk:
                got = length
                return False
            got += len(chunk)
            buf += chunk
            return True

        while state != 'done':
            if state == 'seek_first':
                i = buf.find(dash)
                while i < 0 and refill():
                    i = buf.find(dash)
                if i < 0:
                    state = 'done'
                else:
                    buf = buf[i + len(dash):]
                    state = 'after_delim'
            elif state == 'after_delim':
                # right after a boundary: '--' closes the form, CRLF opens a part
                if buf.startswith(b'--'):
                    state = 'done'
                elif buf.startswith(b'\r\n'):
                    buf = buf[2:]
                    state = 'headers'
                elif refill():
                    pass
                else:
                    state = 'done'
            elif state == 'headers':
                i = buf.find(b'\r\n\r\n')
                while i < 0 and refill():
                    i = buf.find(b'\r\n\r\n')
                if i < 0:
                    state = 'done'
                else:
                    hdr, buf = buf[:i], buf[i + 4:]
                    fm = re.search(rb'filename="?(?P<fn>[^";]+)', hdr)
                    orig_ext = os.path.splitext(
                        fm.group('fn').decode('latin1', 'ignore') if fm else '')[1].lower()
                    tmp = os.path.join(INCOMING, f'.part_{int(time.time() * 1000)}_{saved}')
                    part = [open(tmp, 'wb'), tmp, 0, b'']
                    state = 'body'
            elif state == 'body':
                f, tmp, size, magic = part
                i = buf.find(marker)
                if i >= 0:
                    # marker's leading CRLF belongs to the delimiter and is
                    # already excluded by buf[:i] — chunk is the exact file data
                    chunk, buf = buf[:i], buf[i + 2:]
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
                        magic = (magic + chunk)[:12]
                    part[2], part[3] = size, magic
                    f.close()
                    # buf now starts at the delimiter itself (dash included in marker)
                    # marker consumed up to dash start; advance past dash
                    if buf.startswith(dash):
                        buf = buf[len(dash):]
                    state = 'save_part'
                else:
                    # flush all but a tail shorter than the marker
                    keep = len(marker) - 1
                    if len(buf) > keep:
                        chunk, buf = buf[:-keep], buf[-keep:]
                        f.write(chunk)
                        size += len(chunk)
                        magic = (magic + chunk)[:12]
                        part[2], part[3] = size, magic
                    if size > MAX_FILE:
                        f.close()
                        os.unlink(tmp)
                        raise ValueError(f'file too large (max {MAX_FILE // 2**20}MB)')
                    if not refill():
                        f.close()
                        os.unlink(tmp)
                        raise ValueError('multipart body truncated')
            elif state == 'save_part':
                f, tmp, size, magic = part
                if size == 0:
                    os.unlink(tmp)
                else:
                    ext = sniff_ext(magic, orig_ext)
                    name = f'ref_{int(time.time())}_{saved:02d}{ext}'
                    os.replace(tmp, os.path.join(INCOMING, name))
                    print(f'UPLOAD-SAVED {name} ({size} bytes)', flush=True)
                    saved += 1
                part = None
                state = 'after_delim'
        return saved

if __name__ == '__main__':
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', 8800),
        functools.partial(H, directory=ROOT))
    print('PORTAL READY on 8800 (downloads: / , upload page: /uploader)', flush=True)
    print(f'uploads -> {INCOMING} (max {MAX_FILE // 2**20}MB/file, {MAX_BODY // 2**20}MB/request)', flush=True)
    srv.serve_forever()
