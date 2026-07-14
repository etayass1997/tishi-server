# תישי — שרת

שרת Python/Flask עבור תישי, העוזר האישי — צ'אט עם Claude (כולל תמונות/Vision) + חיפוש אינטרנט (Tavily) + תמלול קול (Groq Whisper) + יצירת PDF בעברית. כולל דף צ'אט (PWA) שרץ מאותו השרת ב-`/`.

## Endpoints
- `GET /health` — סטטוס השרת (בלי אימות).
- `POST /chat` — שיחה. גוף הבקשה: `{"messages": [...], "username": "...", "user_facts": [...]}`. תוכן הודעה יכול להיות מחרוזת או מערך בלוקים בפורמט Claude (טקסט/תמונה) לתמיכה בתמונות.
- `POST /transcribe` — תמלול קובץ שמע ל-multipart form עם שדה `file`. מחזיר `{"transcript": "..."}`.
- `POST /create-pdf` — יצירת PDF בעברית. גוף הבקשה: `{"title": "...", "content": "...", "filename": "..."}`.

`/chat`, `/transcribe` ו-`/create-pdf` דורשים header `X-API-Key` שתואם למשתנה הסביבה `TISHI_API_KEY` (אם הוגדר).

## משתני סביבה
- `ANTHROPIC_API_KEY` — מפתח Claude (חובה)
- `TAVILY_API_KEY` — מפתח חיפוש אינטרנט (אופציונלי, בלעדיו החיפוש לא יעבוד)
- `GROQ_API_KEY` — מפתח לתמלול קול דרך Whisper (אופציונלי, בלעדיו הקלטה/שמע לא יעבדו)
- `TISHI_API_KEY` — סוד משותף לאימות בקשות (מומלץ מאוד כשהשרת חשוף מעבר ל-localhost)
- `PORT` — פורט האזנה (ברירת מחדל 5008)

## הרצה מקומית
```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
ANTHROPIC_API_KEY=... TAVILY_API_KEY=... TISHI_API_KEY=... venv/bin/python app.py
```

## פריסה כשירות systemd (שרת עצמי)
ראה `tishi.service` לדוגמת unit file. מריצים עם gunicorn:
```
venv/bin/gunicorn app:app --bind 0.0.0.0:5008 --timeout 120
```
