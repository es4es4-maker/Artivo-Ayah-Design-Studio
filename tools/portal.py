#!/usr/bin/env python3
"""Download portal + direct upload endpoint for reference images."""
import http.server, functools, os, json, time, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deliverables')
ROOT = os.path.normpath(ROOT)
INCOMING = '/home/user/uploads/incoming'
os.makedirs(INCOMING, exist_ok=True)

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
<p>اختار الصور (ممكن أكتر من صورة)<br>واضغط <b>إرسال</b> — هتظهر رسالة «وصلت» تحت.</p>
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

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/uploader'):
            b = UPLOAD_PAGE.encode()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        if self.path.startswith('/status'):
            fl = sorted(os.listdir(INCOMING))
            self._j({'files': fl, 'count': len(fl)}); return
        super().do_GET()
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def do_POST(self):
        if not self.path.startswith('/upload'):
            self._j({'ok':False,'err':'bad path'},404); return
        try:
            ct = self.headers.get('Content-Type','')
            m = re.search(r'boundary=(.+)$', ct)
            if not m: self._j({'ok':False,'err':'no boundary'},400); return
            boundary = m.group(1).strip().strip('"').encode()
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            saved = 0
            for part in body.split(b'--' + boundary)[1:]:
                if part.startswith(b'--'): continue
                if b'\r\n\r\n' not in part: continue
                hdr, data = part.split(b'\r\n\r\n', 1)
                if data.endswith(b'\r\n'): data = data[:-2]
                if not data: continue
                fn = re.search(r'filename="?([^";]+)"?', hdr.decode('latin1', 'ignore'))
                orig_ext = os.path.splitext(fn.group(1))[1].lower() if fn else ''
                saved += 1
                low = data[:12].lower()
                ext = ('.jpg' if low[:3]==b'\xff\xd8\xff' else
                       '.png' if low[:8]==b'\x89PNG\r\n\x1a\n' else
                       '.zip' if low[:2]==b'PK' else
                       orig_ext if orig_ext in ('.jpg','.jpeg','.png','.webp','.zip') else '.bin')
                name = f'ref_{int(time.time())}_{saved:02d}{ext}'
                path = os.path.join(INCOMING, name)
                with open(path,'wb') as f: f.write(data)
                print(f'UPLOAD-SAVED {path} ({len(data)} bytes)', flush=True)
            self._j({'ok': saved>0, 'count': saved})
        except Exception as e:
            print('UPLOAD-ERR', e, flush=True)
            self._j({'ok':False,'err':str(e)},500)

if __name__ == '__main__':
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', 8800),
        functools.partial(H, directory=ROOT))
    print('PORTAL READY on 8800 (downloads: / , upload page: /uploader)', flush=True)
    srv.serve_forever()
