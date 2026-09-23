# 🕌 ستوديو آرتيفو — ٣٠٠ تصميم قرآني جاهز للطباعة

**٣٠٠ تصميم وول آرت 60×80 سم @ 300DPI** — **١٠ خلفيات × ٣٠ آية مختلفة لكل خلفية** عن الجنة والرحمة والمغفرة والهداية والنور، مع **٣٠٠ موك-أب** بالفريم الذهبي الرفيع على حيطة فاتحة دافئة.

## ✅ ضمانات النص (صفر أخطاء)
- كل آية **منسوخة حرفيًا** من مصدر التنزيل العثماني الرقمي (tanzil / quran-json) مع مقارنة برمجية حرف-بحرف.
- كل مرجع تظهره التصميمات (اسم السورة ورقم الآية) متحقق منه برمجيًا.
- الخط: **Noto Naskh Arabic** — كل التشكيلات ملتصقة ومقروءة؛ أرقام الآيات بترتيبها الصحيح.
- راجعنا الـ ٣٠٠ نص آليًا بعد آخر بناء: **٠ اختلاف نصي** (عدا علامات أنصاف الأحزاب الزخرفية ۞ وعلامات الوقف الصغيرة — مقصود حذفها بصريًا وليست من متن الحروف).
- كل ده بيتراجع بأمر واحد: `python3 tools/verify_all.py` (بيكتب `verify_report.md`).

## 📁 المحتويات
| المكان | المحتوى |
|--------|---------|
| [Release v1.0](https://github.com/es4es4-maker/Artivo-Ayah-Design-Studio/releases/tag/v1.0) | **٣٣ زيب تحميل** (لكل خلفية ٣ أجزاء × ١٠ تصميمات + الموك-أبس ٣ أجزاء) + `SHA256SUMS.txt` |
| `deliverables/plates/` | الخلفيات العشرة + شيت الموافقة |
| `previews/` + `deliverables/previews/` | شيتات المعاينة |
| `deliverables/index.html` | بوابة التحميل والمعاينة |
| `assets/` | ملف الآيات + الخط + المراجع |
| `tools/` | سكريبتات البناء والتحقق والبوابة |

> الماسترز والموك-أبس والزيبات مش متتبعة في git (≈٤.٥ جيجا) — موجودة كاملة في [Release v1.0](https://github.com/es4es4-maker/Artivo-Ayah-Design-Studio/releases/tag/v1.0)، وأي إعادة بناء بتولّدها في `deliverables/` محليًا.

## 🔨 إعادة البناء
```bash
pip install pillow numpy uharfbuzz freetype-py opencv-python-headless
cd tools && npm ci && cd ..          # مصدر النصوص (quran-json@3.1.2 المثبّت)
python3 tools/build_masters.py full  # ٣٠٠ ماستر + ٣٠ زيب طباعة (البروفات في proofs/)
python3 tools/build_mockups_lite.py  # ٣٠٠ موك-أب + ٣ زيب موك-أبس
python3 tools/portal.py              # بوابة التحميل والرفع على :8800
```
- `python3 tools/build_mockups_lite.py fetch-masters` — بينزّل الماسترز من الريلايز لو مش موجودة محليًا (تاج `ARTIVO_RELEASE_TAG`).
- `python3 tools/build_mockups_lite.py zips` — إعادة تغليف زيبات الموك-أبس فقط.
- `python3 tools/select_300.py` — **مرة واحدة فقط**: الاختيار المجمّد A101..A300 — السكريبت **بيرفض** إعادة التشغيل (علشان ميعيدش ترتيب المفاتيح) إلا بـ`--force`.

## 🧪 التحقق الشامل
```bash
python3 tools/verify_all.py --fast     # نصوص + بنية (للـCI على كل PR)
python3 tools/verify_all.py --deep 24  # + فك ترميز ٢٤ صورة بالكامل
python3 tools/verify_all.py --fetch-release v1.0   # ينزّل الزيبات من الريلايز ويفحصها
```
بيقارن كل نص حرف-بحرف بالمصدر المثبّت، ويتأكد من أرقام الآيات (بالأرقام الهندية) وتفرّد الـ٣٠٠ مرجع، ويفحص CRC والأسماء والأعداد لكل الزيبات، ويقرا رؤوس كل الماسترز (JPEG/RGB/7087×9449/300DPI) واتجاه كل موك-أب. سيرفر `verify.yml` بيشغّل الفحص السريع على كل push/PR.

## 🛡️ البوابة (portal.py)
- الرفع محدود: ٢٥ ميجابايت للطلب، ٢٠ ميجابايت للملف الواحد — والجسم بيتنقل على دفعات (64KB) على ملفات مؤقتة مش في الذاكرة.
- الملفات بتنزل في `var/uploads/incoming/` (متجاهلة في git).
- `/status` مقفول إلا بمرور `?token=` مع `ARTIVO_STATUS_TOKEN` في البيئة.
# Trigger release upload after tag creation
