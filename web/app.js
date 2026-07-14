const API_KEY = window.TISHI_API_KEY || '';

const KEYS = { username: 'tishi_username', messages: 'tishi_messages', facts: 'tishi_facts' };

function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
}
function save(key, val) { localStorage.setItem(key, JSON.stringify(val)); }

let username = localStorage.getItem(KEYS.username) || '';
let messages = loadJSON(KEYS.messages, []);
let facts = loadJSON(KEYS.facts, []);

if (!username) {
  username = (prompt('איך קוראים לך?') || 'חבר').trim() || 'חבר';
  localStorage.setItem(KEYS.username, username);
}

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const composerEl = document.getElementById('composer');
const typingEl = document.getElementById('typing');

const PDF_RE = /\[PDF:([^\]]*)\]([\s\S]*?)\[\/PDF\]/;

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function renderMessages() {
  messagesEl.innerHTML = '';
  messages.forEach(m => {
    const bubble = document.createElement('div');
    bubble.className = 'msg ' + (m.role === 'user' ? 'msg-user' : 'msg-assistant');
    bubble.innerHTML = escapeHtml(m.displayContent !== undefined ? m.displayContent : m.content).replace(/\n/g, '<br>');
    messagesEl.appendChild(bubble);

    if (m.pdf) {
      const link = document.createElement('a');
      link.href = m.pdf.url;
      link.download = m.pdf.filename;
      link.className = 'pdf-link';
      link.textContent = '📄 הורד PDF: ' + m.pdf.title;
      messagesEl.appendChild(link);
    }
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function sendMessage(text) {
  messages.push({ role: 'user', content: text });
  save(KEYS.messages, messages);
  renderMessages();
  typingEl.classList.remove('hidden');

  try {
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({
        messages: messages.map(m => ({ role: m.role, content: m.content })),
        username,
        user_facts: facts
      })
    });
    const data = await resp.json();
    typingEl.classList.add('hidden');

    if (data.error) {
      messages.push({ role: 'assistant', content: 'שגיאה: ' + data.error });
      save(KEYS.messages, messages);
      renderMessages();
      return;
    }

    const reply = data.reply || '';
    const match = reply.match(PDF_RE);

    if (match) {
      const title = match[1].trim();
      const content = match[2].trim();
      const remaining = reply.replace(PDF_RE, '').trim();
      const msgObj = { role: 'assistant', content: reply, displayContent: remaining || `יצרתי מסמך: ${title}` };
      messages.push(msgObj);
      save(KEYS.messages, messages);
      renderMessages();
      createPdf(title, content, msgObj);
    } else {
      messages.push({ role: 'assistant', content: reply });
      save(KEYS.messages, messages);
      renderMessages();
    }
  } catch (err) {
    typingEl.classList.add('hidden');
    messages.push({ role: 'assistant', content: 'לא הצלחתי להתחבר לשרת.' });
    save(KEYS.messages, messages);
    renderMessages();
  }
}

async function createPdf(title, content, msgObj) {
  try {
    const resp = await fetch('/create-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({ title, content, filename: title + '.pdf' })
    });
    const data = await resp.json();
    if (data.pdf_base64) {
      const bytes = atob(data.pdf_base64);
      const arr = new Uint8Array(bytes.length);
      for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
      const blob = new Blob([arr], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      msgObj.pdf = { url, filename: data.filename || (title + '.pdf'), title };
      renderMessages();
    }
  } catch (err) {
    console.error('create-pdf failed', err);
  }
}

composerEl.addEventListener('submit', e => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = '';
  autoGrow();
  sendMessage(text);
});

inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    composerEl.requestSubmit();
  }
});

function autoGrow() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
}
inputEl.addEventListener('input', autoGrow);

const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const usernameInput = document.getElementById('username-input');
const factsList = document.getElementById('facts-list');
const factInput = document.getElementById('fact-input');

function renderFacts() {
  factsList.innerHTML = '';
  facts.forEach((f, i) => {
    const chip = document.createElement('div');
    chip.className = 'fact-chip';
    const span = document.createElement('span');
    span.textContent = f;
    const btn = document.createElement('button');
    btn.textContent = '✕';
    btn.dataset.i = i;
    chip.appendChild(span);
    chip.appendChild(btn);
    factsList.appendChild(chip);
  });
}

settingsBtn.addEventListener('click', () => {
  usernameInput.value = username;
  renderFacts();
  settingsModal.classList.remove('hidden');
});

document.getElementById('close-settings-btn').addEventListener('click', () => {
  username = usernameInput.value.trim() || username;
  localStorage.setItem(KEYS.username, username);
  settingsModal.classList.add('hidden');
});

document.getElementById('fact-add-btn').addEventListener('click', () => {
  const v = factInput.value.trim();
  if (!v) return;
  facts.push(v);
  save(KEYS.facts, facts);
  factInput.value = '';
  renderFacts();
});

factsList.addEventListener('click', e => {
  if (e.target.tagName === 'BUTTON') {
    const i = parseInt(e.target.dataset.i, 10);
    facts.splice(i, 1);
    save(KEYS.facts, facts);
    renderFacts();
  }
});

document.getElementById('clear-chat-btn').addEventListener('click', () => {
  if (confirm('לנקות את כל השיחה?')) {
    messages = [];
    save(KEYS.messages, messages);
    renderMessages();
    settingsModal.classList.add('hidden');
  }
});

renderMessages();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
