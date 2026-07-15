import os
import io
import re
import json
import base64
from functools import wraps

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import anthropic
import requests as http_requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from bidi.algorithm import get_display

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEBREW_FONT_PATH = os.path.join(BASE_DIR, 'assets', 'Alef-Regular.ttf')
WEB_DIR = os.path.join(BASE_DIR, 'web')

app = Flask(__name__, static_folder=WEB_DIR, static_url_path='')
CORS(app, origins="*")

API_KEY = os.environ.get('TISHI_API_KEY')
GEMINI_IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')
PDF_RE = re.compile(r'\[PDF:([^\]]*)\]([\s\S]*?)\[/PDF\]')


@app.route('/')
def index():
    with open(os.path.join(WEB_DIR, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    return html.replace('__API_KEY__', API_KEY or '')


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            return fn(*args, **kwargs)
        if API_KEY and request.headers.get('X-API-Key') != API_KEY:
            return jsonify({'error': 'unauthorized'}), 401
        return fn(*args, **kwargs)
    return wrapper


SYSTEM_PROMPT_TEMPLATE = """{intro}

## יכולות
יש לך גישה לאינטרנט דרך כלי חיפוש (web_search). אתה מחובר. כשמישהו שואל אם יש לך גישה לאינטרנט — התשובה היא **כן**.
השתמש ב-web_search בכל פעם שצריך מידע עדכני: מחירים, חדשות, מזג אוויר, אנשים, חברות, שעות פתיחה, כל דבר שמשתנה בזמן.
כשמחפשים — חפש, קרא את התוצאות, וענה בעברית תמציתית. אל תציג לינקים אלא אם מבקשים.

## יצירת מסמך PDF
כשמישהו מבקש ליצור מסמך, סיכום, דוח, מכתב, הצעת מחיר, תוכנית, רשימה מסודרת, חוזה, או כל תוכן שמיועד להורדה — כתוב את התוכן המלא ומסודר בפורמט הזה בדיוק:

[PDF:כותרת המסמך]
תוכן המסמך כאן, שורה אחרי שורה.
[/PDF]

חוקים:
- אל תוסיף שום טקסט לפני הבלוק או אחריו — רק הבלוק עצמו.
- הכותרת תופיע ב-[PDF:...] — בחר כותרת תמציתית ומדויקת.
- התוכן יכול להיות ארוך. כתוב הכל.
- אם צריך מידע מהאינטרנט לצורך המסמך — חפש קודם, ואז כתוב.

## יצירה ועריכת תמונות
יש לך כלי ליצירת תמונות (generate_image). כשמבקשים לצייר, לעצב, ליצור לוגו/איור/תמונה — השתמש בכלי עם prompt מפורט ועשיר בפרטים (מומלץ באנגלית, נותן תוצאה טובה יותר). אם המשתמש צירף תמונה בהודעה האחרונה שלו וביקש לשנות/לשפר/לערוך אותה — הכלי יערוך אותה אוטומטית לפי ההנחיה, אל תבקש ממנו לצרף שוב. אחרי שהתמונה נוצרה היא כבר מוצגת למשתמש — הגב במשפט אחד קצר, אל תתאר את התמונה במילים.

כללי יסוד:
- עברית בלבד.
- עונה בתמציתיות. אם אפשר בשורה אחת — שורה אחת.
- לא מתחיל ב"בהחלט", "כמובן", "שאלה מעולה" או כל ריפוד דומה.
- לא מציג את עצמך ולא מסביר מה אתה.

כשמגיעים עם שאלה פרקטית — עונה ישר. אם חסר מידע — שאלה אחת בלבד, לא יותר.

כשמגיעים עם בעיה או החלטה — לא ממהר לפתרון. שואל קודם: "מה הכי חשוב לך כאן?" ואז עוזר.

כשמגיעים עם משהו רגשי — מקשיב. עונה קצר. לא מציע פתרונות אלא אם מבקשים במפורש.

לעולם אל תאמר משהו שגוי, תמיד תבדוק פעמיים.

אם לא הבנת את השאלה עד הסוף בקש הבהרה.

כשמשהו שגוי — אומר ישר, בלי ריפוד. "זה לא מדויק — " ומסביר בקצרה.

כשלא יודע — חפש קודם. אם גם החיפוש לא עוזר — "לא יודע."

כשמישהו אומר "זכור ש..." — אתה מאשר בקצרה שזכרת, ותשתמש בזה מעכשיו.

{facts_section}"""

TOOLS = [
    {
        "name": "web_search",
        "description": "מחפש מידע עדכני באינטרנט. השתמש כשצריך מידע שלא ידוע לך: חדשות, מחירים, מזג אוויר, אנשים, חברות, מוצרים, תרגומים, או כל מידע שמשתנה בזמן.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "שאילתת חיפוש. כתוב בעברית או אנגלית, תלוי בנושא."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_image",
        "description": "יוצר תמונה חדשה מטקסט, או עורך תמונה שהמשתמש צירף בהודעה האחרונה (אם יש תמונה שם, הכלי עורך אותה לפי ההנחיה; אחרת יוצר תמונה חדשה מאפס). השתמש כשמבקשים ליצור, לצייר, לעצב, או לערוך תמונה/לוגו/איור.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "תיאור מפורט של התמונה הרצויה או של השינוי המבוקש (מומלץ באנגלית)."
                }
            },
            "required": ["prompt"]
        }
    }
]


def web_search(query):
    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        return "TAVILY_API_KEY לא מוגדר בשרת."
    try:
        resp = http_requests.post(
            'https://api.tavily.com/search',
            json={'api_key': api_key, 'query': query, 'max_results': 5},
            timeout=10
        )
        data = resp.json()
        results = data.get('results', [])
        if not results:
            return "לא נמצאו תוצאות."
        parts = []
        for r in results[:5]:
            title = r.get('title', '')
            content = r.get('content', '')
            url = r.get('url', '')
            parts.append(f"{title}\n{content}\n{url}")
        return '\n\n'.join(parts)
    except Exception as e:
        return f"שגיאת חיפוש: {e}"


def extract_last_user_images(msgs):
    """Return image blocks from the most recent genuine human turn (skips tool_result wrapper messages)."""
    for m in reversed(msgs):
        if m.get('role') != 'user':
            continue
        content = m.get('content')
        if isinstance(content, str):
            return []
        if isinstance(content, list):
            if all(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
                continue
            return [
                {'media_type': b['source'].get('media_type', 'image/png'), 'data': b['source'].get('data', '')}
                for b in content
                if isinstance(b, dict) and b.get('type') == 'image' and isinstance(b.get('source'), dict)
            ]
        return []
    return []


def generate_image(prompt, input_images=None):
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        return {'error': 'GOOGLE_API_KEY לא מוגדר בשרת.'}

    parts = []
    for img in (input_images or []):
        parts.append({'inline_data': {'mime_type': img['media_type'], 'data': img['data']}})
    parts.append({'text': prompt})

    try:
        resp = http_requests.post(
            f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent',
            headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'},
            json={'contents': [{'parts': parts}]},
            timeout=60
        )
        data = resp.json()
        candidates = data.get('candidates', [])
        if not candidates:
            err = data.get('error', {}).get('message', 'לא התקבלה תמונה מהמודל.')
            return {'error': err}
        for part in candidates[0].get('content', {}).get('parts', []):
            inline = part.get('inlineData') or part.get('inline_data')
            if inline and inline.get('data'):
                mime = inline.get('mimeType') or inline.get('mime_type') or 'image/png'
                return {'mime_type': mime, 'data': inline['data']}
        return {'error': 'לא התקבלה תמונה מהמודל.'}
    except Exception as e:
        return {'error': f'שגיאת יצירת תמונה: {e}'}


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'claude': bool(os.environ.get('ANTHROPIC_API_KEY')),
        'search': bool(os.environ.get('TAVILY_API_KEY')),
        'transcribe': bool(os.environ.get('GROQ_API_KEY')),
        'image': bool(os.environ.get('GOOGLE_API_KEY')),
        'auth': bool(API_KEY),
    })


@app.route('/transcribe', methods=['POST', 'OPTIONS'])
@require_api_key
def transcribe():
    if request.method == 'OPTIONS':
        return '', 204

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return jsonify({'error': 'GROQ_API_KEY לא מוגדר בשרת'}), 500

    if 'file' not in request.files:
        return jsonify({'error': 'לא התקבל קובץ אודיו'}), 400

    audio = request.files['file']
    try:
        resp = http_requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers={'Authorization': f'Bearer {api_key}'},
            files={'file': (audio.filename or 'audio.webm', audio.stream, audio.mimetype or 'audio/webm')},
            data={'model': 'whisper-large-v3', 'language': 'he', 'response_format': 'json'},
            timeout=120
        )
        if resp.status_code != 200:
            detail = resp.json().get('error', {}).get('message', resp.text[:200])
            return jsonify({'error': f'שגיאת תמלול: {detail}'}), 502
        text = resp.json().get('text', '').strip()
        if not text:
            return jsonify({'error': 'התמלול חזר ריק'}), 422
        return jsonify({'transcript': text})
    except Exception as e:
        return jsonify({'error': f'שגיאת תמלול: {e}'}), 500


@app.route('/chat', methods=['POST', 'OPTIONS'])
@require_api_key
def chat():
    if request.method == 'OPTIONS':
        return '', 204

    data = request.json
    messages = data.get('messages', [])
    username = (data.get('username') or '').strip()
    user_facts = data.get('user_facts', [])

    intro = f"אתה תישי — הסוכן האישי של {username}." if username else "אתה תישי — עוזר אישי כללי, שיודע לענות על כל דבר."

    facts_section = ""
    if user_facts:
        lines = "\n".join(f"- {f}" for f in user_facts)
        who = username or "המשתמש"
        facts_section = f"מה שאתה זוכר על {who}:\n{lines}"

    system = SYSTEM_PROMPT_TEMPLATE.replace('{intro}', intro).replace('{facts_section}', facts_section)

    def generate():
        try:
            for event in stream_claude(messages, system):
                yield json.dumps(event, ensure_ascii=False) + '\n'
        except Exception as e:
            yield json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False) + '\n'

    resp = Response(generate(), mimetype='application/x-ndjson')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


def stream_claude(messages, system):
    """Streams the Claude conversation as a sequence of small event dicts.

    Event types: delta, tool_start, image, pdf_start, pdf, error, done.
    PDF blocks ([PDF:title]...[/PDF]) are detected server-side and never leaked
    as raw markup — per system-prompt contract they are always the entire reply,
    so the first ~5 chars of a turn's text decide whether it's a PDF turn.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        yield {'type': 'error', 'error': 'ANTHROPIC_API_KEY לא מוגדר בשרת'}
        yield {'type': 'done'}
        return

    client = anthropic.Anthropic(api_key=api_key)
    msgs = list(messages)

    for _ in range(5):
        text_buf = ''
        pdf_mode = None   # None = undetermined, False = plain text, True = pdf block
        pdf_title = None

        with client.messages.stream(
            model='claude-sonnet-5',
            max_tokens=5000,
            thinking={'type': 'disabled'},
            system=system,
            tools=TOOLS,
            messages=msgs
        ) as stream:
            for event in stream:
                if event.type == 'content_block_start' and event.content_block.type == 'tool_use':
                    yield {'type': 'tool_start', 'tool': event.content_block.name}
                elif event.type == 'content_block_delta' and event.delta.type == 'text_delta':
                    text_buf += event.delta.text
                    if pdf_mode is None:
                        if len(text_buf) >= 5:
                            pdf_mode = text_buf.startswith('[PDF:')
                            if not pdf_mode:
                                yield {'type': 'delta', 'text': text_buf}
                    elif pdf_mode is False:
                        yield {'type': 'delta', 'text': event.delta.text}
                    elif pdf_title is None:
                        close_idx = text_buf.find(']')
                        if close_idx != -1:
                            pdf_title = text_buf[5:close_idx]
                            yield {'type': 'pdf_start', 'title': pdf_title}
            final = stream.get_final_message()

        if pdf_mode is None and text_buf:
            yield {'type': 'delta', 'text': text_buf}

        if final.stop_reason == 'tool_use':
            tool_block = next(b for b in final.content if b.type == 'tool_use')
            msgs.append({'role': 'assistant', 'content': final.content})

            if tool_block.name == 'generate_image':
                prompt_text = tool_block.input.get('prompt', '')
                input_images = extract_last_user_images(msgs)
                result = generate_image(prompt_text, input_images)
                if 'error' in result:
                    msgs.append({'role': 'user', 'content': [{
                        'type': 'tool_result', 'tool_use_id': tool_block.id,
                        'content': result['error'], 'is_error': True
                    }]})
                else:
                    yield {'type': 'image', 'mime': result['mime_type'], 'data': result['data']}
                    msgs.append({'role': 'user', 'content': [{
                        'type': 'tool_result', 'tool_use_id': tool_block.id,
                        'content': [
                            {'type': 'image', 'source': {'type': 'base64', 'media_type': result['mime_type'], 'data': result['data']}},
                            {'type': 'text', 'text': 'התמונה נוצרה בהצלחה והוצגה למשתמש.'}
                        ]
                    }]})
            else:
                search_result = web_search(tool_block.input.get('query', ''))
                msgs.append({'role': 'user', 'content': [{
                    'type': 'tool_result', 'tool_use_id': tool_block.id, 'content': search_result
                }]})
            continue

        if pdf_mode:
            match = PDF_RE.search(text_buf)
            if match:
                yield {'type': 'pdf', 'title': match.group(1).strip(), 'content': match.group(2).strip()}
        yield {'type': 'done'}
        return

    yield {'type': 'error', 'error': 'לא הצלחתי לסיים את הבקשה.'}
    yield {'type': 'done'}


def ensure_hebrew_font():
    if 'Alef' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Alef', HEBREW_FONT_PATH))


@app.route('/create-pdf', methods=['POST', 'OPTIONS'])
@require_api_key
def create_pdf():
    if request.method == 'OPTIONS':
        return '', 204

    data = request.json or {}
    title = data.get('title', '')
    content = data.get('content', '')
    filename = data.get('filename', 'document.pdf')

    try:
        ensure_hebrew_font()

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        margin = 40

        c.setFont('Alef', 22)
        c.drawRightString(width - margin, height - 60, get_display(title))

        c.setLineWidth(0.5)
        c.line(margin, height - 72, width - margin, height - 72)

        c.setFont('Alef', 13)
        y = height - 100
        line_height = 20

        for paragraph in content.split('\n'):
            words = paragraph.split(' ')
            line = ''
            for word in words:
                test = (word + ' ' + line).strip()
                if c.stringWidth(test, 'Alef', 13) > (width - 2 * margin):
                    if y < margin + line_height:
                        c.showPage()
                        c.setFont('Alef', 13)
                        y = height - margin
                    c.drawRightString(width - margin, y, get_display(line.strip()))
                    y -= line_height
                    line = word
                else:
                    line = test
            if line:
                if y < margin + line_height:
                    c.showPage()
                    c.setFont('Alef', 13)
                    y = height - margin
                c.drawRightString(width - margin, y, get_display(line.strip()))
                y -= line_height
            y -= 4

        c.save()
        pdf_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return jsonify({'pdf_base64': pdf_b64, 'filename': filename})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5008))
    app.run(host='0.0.0.0', port=port)
