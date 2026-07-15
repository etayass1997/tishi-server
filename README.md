# תישי — שרת

שרת Python/Flask עבור תישי, העוזר האישי — צ'אט סטרימינג עם Claude (כולל תמונות/Vision) + חיפוש אינטרנט (Tavily) + יצירה ועריכת תמונות (Gemini) + תמלול קול (Groq Whisper) + יצירת PDF בעברית. כולל דף צ'אט (PWA) שרץ מאותו השרת ב-`/`, וכן לקוח טרמינל (`tishi_cli.py`).

## Endpoints
- `GET /health` — סטטוס השרת (בלי אימות).
- `POST /chat` — שיחה בסטרימינג. גוף הבקשה: `{"messages": [...], "username": "...", "user_facts": [...]}`. תוכן הודעה יכול להיות מחרוזת או מערך בלוקים בפורמט Claude (טקסט/תמונה) לתמיכה בתמונות. **התגובה זורמת** כ-NDJSON (`application/x-ndjson`, שורה אחת = אירוע JSON אחד), לא JSON יחיד. סוגי אירועים:
  - `{"type":"delta","text":"..."}` — קטע טקסט להוספה (סטרימינג "תוך כדי מחשבה").
  - `{"type":"tool_start","tool":"web_search"|"generate_image"}` — תישי התחיל להשתמש בכלי.
  - `{"type":"image","mime":"image/png","data":"<base64>"}` — תמונה שנוצרה/נערכה.
  - `{"type":"pdf_start","title":"..."}` — תישי מרכיב מסמך PDF.
  - `{"type":"pdf","title":"...","content":"..."}` — תוכן המסמך סופי; הלקוח קורא ל-`/create-pdf` כדי לקבל את הקובץ.
  - `{"type":"error","error":"..."}`
  - `{"type":"done"}` — סוף התגובה.
- `POST /transcribe` — תמלול קובץ שמע ל-multipart form עם שדה `file`. מחזיר `{"transcript": "..."}`.
- `POST /create-pdf` — יצירת PDF בעברית. גוף הבקשה: `{"title": "...", "content": "...", "filename": "..."}`.

`/chat`, `/transcribe` ו-`/create-pdf` דורשים header `X-API-Key` שתואם למשתנה הסביבה `TISHI_API_KEY` (אם הוגדר).

## יצירה ועריכת תמונות
תישי יכול לצייר תמונה חדשה מטקסט או לערוך תמונה שצורפה להודעה האחרונה, דרך כלי (`generate_image`) שקורא ל-Gemini (`gemini-2.5-flash-image`, aka nano-banana). דורש `GOOGLE_API_KEY`. בלעדיו הכלי מחזיר שגיאה בעברית והשיחה ממשיכה כרגיל.

## משתני סביבה
- `ANTHROPIC_API_KEY` — מפתח Claude (חובה)
- `TAVILY_API_KEY` — מפתח חיפוש אינטרנט (אופציונלי, בלעדיו החיפוש לא יעבוד)
- `GOOGLE_API_KEY` — מפתח Gemini ליצירה/עריכה של תמונות (אופציונלי, בלעדיו `generate_image` לא יעבוד)
- `GEMINI_IMAGE_MODEL` — מודל התמונות של Gemini (אופציונלי, ברירת מחדל `gemini-2.5-flash-image`)
- `GROQ_API_KEY` — מפתח לתמלול קול דרך Whisper (אופציונלי, בלעדיו הקלטה/שמע לא יעבדו)
- `TISHI_API_KEY` — סוד משותף לאימות בקשות (מומלץ מאוד כשהשרת חשוף מעבר ל-localhost)
- `PORT` — פורט האזנה (ברירת מחדל 5008)

## הרצה מקומית
```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
ANTHROPIC_API_KEY=... TAVILY_API_KEY=... GOOGLE_API_KEY=... TISHI_API_KEY=... venv/bin/python app.py
```

הערה: אם מריצים ישירות עם `python app.py` על Windows יחד עם Python ישן (3.8) עלול לצוץ `SyntaxError: Non-UTF-8 code` — זה תקלה ידועה של הריצה הישירה (tokenizer) על Windows עם Python 3.8 ולא קשור לתוכן הקובץ. ריצה דרך `gunicorn app:app` (ה-import הרגיל, כמו בפריסה בפועל) לא מושפעת.

## לקוח טרמינל
`tishi_cli.py` הוא לקוח טרמינל בעברית, ללא תלויות חיצוניות (Python סטנדרטי בלבד), שמדבר עם השרת דרך `/chat` בזמן אמת:
```
TISHI_URL=http://192.168.0.199:5008 TISHI_API_KEY=... python tishi_cli.py
```
פקודות זמינות בתוך הצ'אט: `/שם`, `/זכור`, `/תמונה <נתיב>` (או `/תמונה last` לעריכת התמונה האחרונה שנוצרה), `/נקה`, `/עזרה`, `/יציאה`. תמונות שנוצרות נשמרות ב-`~/tishi_images`, ומסמכי PDF ב-`~/tishi_pdfs`.

## פריסה כשירות systemd (שרת עצמי)
ראה `tishi.service` לדוגמת unit file. מריצים עם gunicorn:
```
venv/bin/gunicorn app:app --bind 0.0.0.0:5008 --timeout 120
```
אם יש reverse proxy (nginx וכד') מול השרת — יש לוודא `proxy_buffering off;` כדי שהסטרימינג יגיע ללקוח בזמן אמת ולא ייחסם עד לסיום התגובה.
