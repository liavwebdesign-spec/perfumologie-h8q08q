# perfumologie: דוגמית גלילה

דוגמית של חמש סצנות גלילה לבקבוק 400 מ"ל, נבנתה עבור הצעת המחיר לפני אישור הפרויקט. לא לאינדוקס (`noindex`).

- `site/`: הדף (`index.html`) והפריימים. `frames/` 1280x720 למחשב, `frames-lo/` 640x360 לטעינה ראשונה, `frames-pt/` 405x720 לטלפון, מרונדרים בנפרד במצלמה לאורך.
- `blender/perfumologie.py`: הסצנות כקוד. רינדור מקומי ב-Blender 5.2 (Cycles), בלי קבצי מקור חיצוניים:
  `blender.exe -b --factory-startup -P blender/perfumologie.py -- --mode hi|pt --scenes 1,2,3,4,5 --samples 64 --out render/hi`
- הפרסום: GitHub Actions מעלה את `site/` ל-Pages בכל push ל-main.
