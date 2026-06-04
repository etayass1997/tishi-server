from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import anthropic
import os
import traceback
import io
 
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
כשמבקשים ממך ליצור קובץ כלשהו — חובה להשתמש בפורמט הזה בדיוק:
 
[FILE:שם_קובץ.סיומת]
תוכן הקובץ כאן
[/FILE]
 
דוגמה:
[FILE:רשימה.txt]
פריט 1
פריט 2
[/FILE]
 
חוקים:
- אל תכתוב את תוכן הקובץ בשום דרך אחרת
- סיומות נתמכות: .txt .md .csv .html .json .docx .pdf
- לכותרות השתמש ב-# ו-##, לרשימות השתמש ב- -"""
 
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
 
@app.route('/pdf', methods=['POST', 'OPTIONS'])
def create_pdf():
    if request.method == 'OPTIONS':
        return '', 204
 
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.enums import TA_RIGHT
 
        data = request.json
        content = data.get('content', '')
        filename = data.get('filename', 'document.pdf')
 
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
 
        styles = getSampleStyleSheet()
        rtl_style = ParagraphStyle('RTL', parent=styles['Normal'],
                                   alignment=TA_RIGHT, fontSize=12,
                                   fontName='Helvetica', leading=18)
        h1_style = ParagraphStyle('H1', parent=rtl_style, fontSize=18,
                                  fontName='Helvetica-Bold', spaceAfter=12)
        h2_style = ParagraphStyle('H2', parent=rtl_style, fontSize=14,
                                  fontName='Helvetica-Bold', spaceAfter=8)
 
        story = []
        for line in content.split('\n'):
            if line.startswith('# '):
                story.append(Paragraph(line[2:], h1_style))
            elif line.startswith('## '):
                story.append(Paragraph(line[3:], h2_style))
            elif line.startswith('- '):
                story.append(Paragraph('• ' + line[2:], rtl_style))
            elif line.strip():
                story.append(Paragraph(line, rtl_style))
            else:
                story.append(Spacer(1, 6))
 
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf',
                        as_attachment=True, download_name=filename)
 
    except ImportError:
        return jsonify({'error': 'reportlab לא מותקן'}), 500
    except Exception as e:
        print("PDF ERROR:", traceback.format_exc())
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
 
