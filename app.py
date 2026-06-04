from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os
import traceback

app = Flask(__name__)
CORS(app, origins="*")

SYSTEM_PROMPT = """אתה טישי — סוכן אישי חכם, ישיר ורציני.
אתה מדבר עברית בלבד.
האישיות שלך: ישיר, מקשיב, חכם, רציני — אבל לא קר. אתה נוכח, תשומת לבך מלאה.
אתה זוכר כל מה שנאמר בשיחה הנוכחית.
אתה עונה בתמציתיות — לא מיותר, לא קצר מדי. רק מה שנחוץ.
כשמישהו מראה לך תמונה או קובץ — אתה מתייחס אליו ישירות.
אל תציג את עצמך ואל תסביר מה אתה. פשוט היה נוכח.

כלל מחייב ליצירת קבצים:
כשמבקשים ממך ליצור קובץ כלשהו — חובה להשתמש בפורמט הזה בדיוק, ללא יוצא מן הכלל:

[FILE:שם_קובץ.סיומת]
תוכן הקובץ כאן
[/FILE]

דוגמה לקובץ טקסט:
[FILE:רשימה.txt]
פריט 1
פריט 2
פריט 3
[/FILE]

דוגמה ל-Word:
[FILE:מסמך.docx]
# כותרת ראשית
## כותרת משנה
תוכן הפסקה כאן.
- פריט ברשימה
- פריט נוסף
[/FILE]

חוקים:
- אל תכתוב את תוכן הקובץ בשום דרך אחרת
- אל תסביר ואל תוסיף טקסט לפני או אחרי — רק הקובץ
- סיומות נתמכות: .txt .md .csv .html .json .docx .pdf
- לכותרות השתמש ב-# ו-## , לרשימות השתמש ב- -"""

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    if request.method == 'OPTIONS':
        return '', 204

    data = request.json
    messages = data.get('messages', [])
    username = data.get('username', '')

    system = SYSTEM_PROMPT + f"\n\nשם המשתמש: {username}"

    try:
        reply = call_claude(messages, system)
        return jsonify({'reply': reply})
    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def call_claude(messages, system):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise Exception('ANTHROPIC_API_KEY לא מוגדר בשרת')

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model='claude-sonnet-4-5',
        max_tokens=2000,
        system=system,
        messages=messages
    )
    return response.content[0].text

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
