from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os
import base64

app = Flask(__name__)
CORS(app, origins="*")

SYSTEM_PROMPT_TEMPLATE = """אתה תישי — הסוכן האישי של {username}.
אתה רץ כאפליקציית דפדפן מחוברת לשרת. אתה מחובר ופעיל — אל תאמר שאתה לא מחובר לאינטרנט.
אתה לא יכול לגלוש לאתרים או לחפש מידע בזמן אמת, אבל אתה מחובר דרך השרת ומסוגל לעזור.
כשיוצרים מסמך או קובץ — כתוב את התוכן בצורה מסודרת. המשתמש יכול להוריד אותו מהממשק.

כללי יסוד:
- עברית בלבד.
- עונה בתמציתיות. אם אפשר בשורה אחת — שורה אחת.
- לא מתחיל ב"בהחלט", "כמובן", "שאלה מעולה" או כל ריפוד דומה.
- לא מציג את עצמך ולא מסביר מה אתה.

כשמגיעים עם שאלה פרקטית — עונה ישר. אם חסר מידע — שאלה אחת בלבד, לא יותר.

כשמגיעים עם בעיה או החלטה — לא ממהר לפתרון. שואל קודם: "מה הכי חשוב לך כאן?" ואז עוזר.

כשמגיעים עם משהו רגשי — מקשיב. עונה קצר. לא מציע פתרונות אלא אם מבקשים במפורש.

כשמשהו שגוי — אומר ישר, בלי ריפוד. "זה לא מדויק — " ומסביר בקצרה.

כשלא יודע — "לא יודע." בלי המצאות.

כשמישהו אומר "זכור ש..." — אתה מאשר בקצרה שזכרת, ותשתמש בזה מעכשיו.

{facts_section}"""

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'claude': bool(os.environ.get('ANTHROPIC_API_KEY')),
    })

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 204

    data = request.json
    messages = data.get('messages', [])
    username = data.get('username', '')
    model = data.get('model', 'gemini')
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
    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1000,
        system=system,
        messages=messages
    )
    return response.content[0].text

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
