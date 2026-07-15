#!/usr/bin/env python3
"""לקוח טרמינל לתישי — משוחח עם שרת ה-Flask דרך /chat בזמן אמת (סטרימינג).

הרצה:
    TISHI_URL=http://192.168.0.199:5008 TISHI_API_KEY=... python tishi_cli.py

ללא משתני סביבה ברירת המחדל היא http://localhost:5008 ובלי מפתח.
"""
import base64
import codecs
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

TISHI_URL = os.environ.get('TISHI_URL', 'http://localhost:5008').rstrip('/')
API_KEY = os.environ.get('TISHI_API_KEY', '')

CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.tishi_cli.json')
IMAGES_DIR = os.path.join(os.path.expanduser('~'), 'tishi_images')
PDF_DIR = os.path.join(os.path.expanduser('~'), 'tishi_pdfs')

if sys.platform == 'win32':
    os.system('')  # enables ANSI escape processing on Windows terminals

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8')
        except Exception:
            pass

RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'
CYAN = '\033[36m'
GREEN = '\033[32m'
RED = '\033[31m'
YELLOW = '\033[33m'


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'username': '', 'facts': []}


def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def print_help():
    print(f"""{DIM}פקודות:
  /שם <שם>          קובע איך תישי יקרא לך (נשמר)
  /זכור <עובדה>      מוסיף עובדה שתישי יזכור עליך (נשמר)
  /תמונה <נתיב>      מצרף תמונה מקומית להודעה הבאה (לעריכה/ניתוח)
  /תמונה last        מצרף את התמונה האחרונה שתישי יצר, לעריכה נוספת
  /נקה               מנקה את היסטוריית השיחה הנוכחית
  /עזרה              מציג עזרה זו
  /יציאה             יציאה
{RESET}""")


def post_stream(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(TISHI_URL + path, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    if API_KEY:
        req.add_header('X-API-Key', API_KEY)
    decoder = codecs.getincrementaldecoder('utf-8')()
    with urllib.request.urlopen(req, timeout=180) as resp:
        buf = ''
        while True:
            chunk = resp.read(512)
            if not chunk:
                buf += decoder.decode(b'', final=True)
                break
            buf += decoder.decode(chunk)
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                if line.strip():
                    yield json.loads(line)
        if buf.strip():
            yield json.loads(buf)


def post_json(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(TISHI_URL + path, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    if API_KEY:
        req.add_header('X-API-Key', API_KEY)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode('utf-8'))


def load_image_file(path):
    path = path.strip().strip('"')
    if not os.path.isfile(path):
        print(f"{RED}לא נמצא קובץ: {path}{RESET}")
        return None
    mime, _ = mimetypes.guess_type(path)
    if not mime or not mime.startswith('image/'):
        print(f"{RED}זה לא נראה כמו קובץ תמונה: {path}{RESET}")
        return None
    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('ascii')
    return {'media_type': mime, 'data': data}


def save_image_bytes(mime, b64data):
    os.makedirs(IMAGES_DIR, exist_ok=True)
    ext = mimetypes.guess_extension(mime) or '.png'
    if ext == '.jpe':
        ext = '.jpg'
    filename = f"tishi_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    out_path = os.path.join(IMAGES_DIR, filename)
    with open(out_path, 'wb') as f:
        f.write(base64.b64decode(b64data))
    return out_path


def sanitize_filename(name):
    keep = [c for c in name if c.isalnum() or c in ' _-']
    cleaned = ''.join(keep).strip() or 'document'
    return cleaned[:80]


def main():
    cfg = load_config()
    username = cfg.get('username', '')
    facts = cfg.get('facts', [])
    history = []
    pending_image = None
    last_generated_image = None  # {'media_type', 'data'}

    print(f"{BOLD}{CYAN}תישי{RESET} — עוזר אישי · {DIM}{TISHI_URL}{RESET}")
    print(f"{DIM}הקלד /עזרה לפקודות.{RESET}\n")

    while True:
        try:
            prompt_label = f"{BOLD}{username or 'אתה'}:{RESET} "
            text = input(prompt_label).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text in ('/יציאה', '/exit', '/quit'):
            break
        if text in ('/עזרה', '/help'):
            print_help()
            continue
        if text in ('/נקה', '/clear'):
            history = []
            print(f"{DIM}השיחה נוקתה.{RESET}")
            continue
        if text.startswith('/שם '):
            username = text[len('/שם '):].strip()
            cfg['username'] = username
            save_config(cfg)
            print(f"{DIM}שמור. תישי יקרא לך {username}.{RESET}")
            continue
        if text.startswith('/זכור '):
            fact = text[len('/זכור '):].strip()
            if fact:
                facts.append(fact)
                cfg['facts'] = facts
                save_config(cfg)
                print(f"{DIM}זכרתי: {fact}{RESET}")
            continue
        if text.startswith('/תמונה '):
            arg = text[len('/תמונה '):].strip()
            if arg == 'last':
                if last_generated_image:
                    pending_image = last_generated_image
                    print(f"{DIM}התמונה האחרונה צורפה לעריכה.{RESET}")
                else:
                    print(f"{DIM}עדיין לא נוצרה תמונה בשיחה הזו.{RESET}")
            else:
                img = load_image_file(arg)
                if img:
                    pending_image = img
                    print(f"{DIM}תמונה צורפה: {os.path.basename(arg)}{RESET}")
            continue

        content = text
        if pending_image:
            content = [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': pending_image['media_type'], 'data': pending_image['data']}},
                {'type': 'text', 'text': text}
            ]
            pending_image = None
        history.append({'role': 'user', 'content': content})

        sys.stdout.write(f"{BOLD}{CYAN}תישי:{RESET} ")
        sys.stdout.flush()

        assistant_text = ''
        had_output = False
        status_active = False
        error_occurred = False

        try:
            for event in post_stream('/chat', {'messages': history, 'username': username, 'user_facts': facts}):
                etype = event.get('type')
                if etype == 'delta':
                    if status_active:
                        sys.stdout.write('\n')
                        status_active = False
                    sys.stdout.write(event['text'])
                    sys.stdout.flush()
                    assistant_text += event['text']
                    had_output = True
                elif etype == 'tool_start':
                    label = ('🎨 מייצר תמונה...' if event.get('tool') == 'generate_image'
                             else '🔎 מחפש באינטרנט...' if event.get('tool') == 'web_search'
                             else 'עובד על זה...')
                    sys.stdout.write(f"\n{DIM}{label}{RESET}\n")
                    sys.stdout.flush()
                    status_active = False
                    had_output = True
                elif etype == 'pdf_start':
                    sys.stdout.write(f"\n{DIM}📄 יוצר מסמך: {event.get('title', '')}...{RESET}\n")
                    sys.stdout.flush()
                    had_output = True
                elif etype == 'image':
                    mime = event.get('mime', 'image/png')
                    data = event.get('data', '')
                    last_generated_image = {'media_type': mime, 'data': data}
                    path = save_image_bytes(mime, data)
                    sys.stdout.write(f"\n{GREEN}🖼 תמונה נשמרה: {path}{RESET}\n{DIM}(השתמש ב-/תמונה last כדי לערוך אותה בהמשך){RESET}\n")
                    sys.stdout.flush()
                    had_output = True
                elif etype == 'pdf':
                    title = event.get('title', 'document')
                    try:
                        result = post_json('/create-pdf', {
                            'title': title, 'content': event.get('content', ''),
                            'filename': sanitize_filename(title) + '.pdf'
                        })
                        if result.get('pdf_base64'):
                            os.makedirs(PDF_DIR, exist_ok=True)
                            out_path = os.path.join(PDF_DIR, sanitize_filename(title) + '.pdf')
                            with open(out_path, 'wb') as f:
                                f.write(base64.b64decode(result['pdf_base64']))
                            assistant_text = f"יצרתי מסמך: {title}"
                            sys.stdout.write(f"{assistant_text}\n{GREEN}📄 נשמר: {out_path}{RESET}\n")
                        else:
                            sys.stdout.write(f"\n{RED}יצירת ה-PDF נכשלה: {result.get('error', '')}{RESET}\n")
                    except Exception as e:
                        sys.stdout.write(f"\n{RED}יצירת ה-PDF נכשלה: {e}{RESET}\n")
                    sys.stdout.flush()
                    had_output = True
                elif etype == 'error':
                    sys.stdout.write(f"\n{RED}שגיאה: {event.get('error', '')}{RESET}\n")
                    sys.stdout.flush()
                    error_occurred = True
                    had_output = True
                elif etype == 'done':
                    pass
        except KeyboardInterrupt:
            sys.stdout.write(f"\n{DIM}[בוטל]{RESET}\n")
            history.pop()
            continue
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            sys.stdout.write(f"\n{RED}לא הצלחתי להתחבר לשרת ({TISHI_URL}): {e}{RESET}\n")
            history.pop()
            continue

        if not had_output:
            sys.stdout.write(f"{DIM}(אין תגובה){RESET}")
        print('\n')

        if not error_occurred:
            history.append({'role': 'assistant', 'content': assistant_text})


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
