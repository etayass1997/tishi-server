from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests as http_requests
import os
import base64
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from bidi.algorithm import get_display

HEBREW_FONT_REGISTERED = False
HEBREW_FONT_PATH = '/tmp/alef-regular.ttf'

def ensure_hebrew_font():
    global HEBREW_FONT_REGISTERED
    if HEBREW_FONT_REGISTERED:
        return
    if not os.path.exists(HEBREW_FONT_PATH):
        font_url = 'https://github.com/google/fonts/raw/main/ofl/alef/Alef-Regular.ttf'
        resp = http_requests.get(font_url, timeout=20)
        resp.raise_for_status()
        with open(HEBREW_FONT_PATH, 'wb') as f:
            f.write(resp.content)
    pdfmetrics.registerFont(TTFont('Alef', HEBREW_FONT_PATH))
    HEBREW_FONT_REGISTERED = True

app = Flask(__name__)
CORS(app, origins="*")

SYSTEM_PROMPT_TEMPLATE = """אתה תישי — הסוכן האישי של {username}.

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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'claude': bool(os.environ.get('ANTHROPIC_API_KEY')),
        'search': bool(os.environ.get('TAVILY_API_KEY')),
    })

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 204

    data = request.json
    messages = data.get('messages', [])
    username = data.get('username', '')
    user_facts = data.get('user_facts', [])

    facts_section = ""
    if user_facts:
        lines = "\n".join(f"- {f}" for f in user_facts)
        facts_section = f"מה שאתה זוכר על {username}:\n{lines}"

    system = SYSTEM_PROMPT_TEMPLATE.replace('{username}', username).replace('{facts_section}', facts_section)

    try:
        reply = call_claude(messages, system)
        return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def call_claude(messages, system):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise Exception('ANTHROPIC_API_KEY לא מוגדר בשרת')

    client = anthropic.Anthropic(api_key=api_key)
    msgs = list(messages)

    for _ in range(5):
        response = client.messages.create(
            model='claude-sonnet-5',
            max_tokens=5000,
            thinking={'type': 'disabled'},
            system=system,
            tools=TOOLS,
            messages=msgs
        )

        if response.stop_reason == 'tool_use':
            tool_block = next(b for b in response.content if b.type == 'tool_use')
            search_result = web_search(tool_block.input.get('query', ''))

            msgs.append({'role': 'assistant', 'content': response.content})
            msgs.append({
                'role': 'user',
                'content': [{
                    'type': 'tool_result',
                    'tool_use_id': tool_block.id,
                    'content': search_result
                }]
            })
        else:
            text_blocks = [b for b in response.content if hasattr(b, 'text')]
            return text_blocks[0].text if text_blocks else ''

    return 'לא הצלחתי לסיים את החיפוש.'

@app.route('/create-pdf', methods=['POST', 'OPTIONS'])
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
