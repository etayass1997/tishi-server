from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import requests as http_requests
import os
import base64

app = Flask(__name__)
CORS(app, origins="*")

SYSTEM_PROMPT_TEMPLATE = """אתה תישי — הסוכן האישי של {username}.

## יכולות
יש לך גישה לאינטרנט דרך כלי חיפוש (web_search). אתה מחובר. כשמישהו שואל אם יש לך גישה לאינטרנט — התשובה היא **כן**.
השתמש ב-web_search בכל פעם שצריך מידע עדכני: מחירים, חדשות, מזג אוויר, אנשים, חברות, שעות פתיחה, כל דבר שמשתנה בזמן.
כשמחפשים — חפש, קרא את התוצאות, וענה בעברית תמציתית. אל תציג לינקים אלא אם מבקשים.
כשיוצרים מסמך — כתוב תוכן מסודר. המשתמש יכול להוריד אותו.

כללי יסוד:
- עברית בלבד.
- עונה בתמציתיות. אם אפשר בשורה אחת — שורה אחת.
- לא מתחיל ב"בהחלט", "כמובן", "שאלה מעולה" או כל ריפוד דומה.
- לא מציג את עצמך ולא מסביר מה אתה.

כשמגיעים עם שאלה פרקטית — עונה ישר. אם חסר מידע — שאלה אחת בלבד, לא יותר.

כשמגיעים עם בעיה או החלטה — לא ממהר לפתרון. שואל קודם: "מה הכי חשוב לך כאן?" ואז עוזר.

כשמגיעים עם משהו רגשי — מקשיב. עונה קצר. לא מציע פתרונות אלא אם מבקשים במפורש.

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
            model='claude-sonnet-4-6',
            max_tokens=2000,
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
