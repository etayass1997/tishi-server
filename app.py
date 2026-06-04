from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import anthropic
import os
import base64
import traceback

app = Flask(__name__)
CORS(app, origins="*")

SYSTEM_PROMPT = """אתה טישי — סוכן אישי חכם, ישיר ורציני.
אתה מדבר עברית בלבד.
האישיות שלך: ישיר, מקשיב, חכם, רציני — אבל לא קר. אתה נוכח, תשומת לבך מלאה.
אתה זוכר כל מה שנאמר בשיחה הנוכחית.
אתה עונה בתמציתיות — לא מיותר, לא קצר מדי. רק מה שנחוץ.
כשמישהו מראה לך תמונה או קובץ — אתה מתייחס אליו ישירות.
כשמבקשים ממך ליצור קובץ — אתה כותב את התוכן בצורה מסודרת.
אל תציג את עצמך ואל תסביר מה אתה. פשוט היה נוכח."""

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
    model = data.get('model', 'gemini')

    system = SYSTEM_PROMPT + f"\n\nשם המשתמש: {username}"

    try:
        if model == 'claude':
            reply = call_claude(messages, system)
        else:
            reply = call_gemini(messages, system)
        return jsonify({'reply': reply})
    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def call_gemini(messages, system):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise Exception('GEMINI_API_KEY לא מוגדר בשרת')

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=system
    )

    gemini_messages = []
    for m in messages:
        role = 'user' if m['role'] == 'user' else 'model'
        content = m['content']

        if isinstance(content, str):
            parts = [content]
        else:
            parts = []
            for block in content:
                if block.get('type') == 'text':
                    parts.append(block['text'])
                elif block.get('type') == 'image':
                    src = block.get('source', {})
                    img_data = base64.b64decode(src.get('data', ''))
                    parts.append({'mime_type': src.get('media_type', 'image/jpeg'), 'data': img_data})

        gemini_messages.append({'role': role, 'parts': parts})

    response = model.generate_content(gemini_messages)
    return response.text

def call_claude(messages, system):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise Exception('ANTHROPIC_API_KEY לא מוגדר בשרת')

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=1000,
        system=system,
        messages=messages
    )
    return response.content[0].text

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
