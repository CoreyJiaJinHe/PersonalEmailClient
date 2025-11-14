const msgListEl = document.getElementById('messageList');
const statusEl = document.getElementById('status');
const detailSubjectEl = document.getElementById('detailSubject');
const detailMetaEl = document.getElementById('detailMeta');
const detailBodyEl = document.getElementById('detailBody');
const deleteBtn = document.getElementById('deleteBtn');
const restoreBtn = document.getElementById('restoreBtn');
const detailToolbarEl = document.getElementById('detailToolbar');

let currentMessageId = null;
let showingTrash = false;
let currentSearch = '';
let currentPage = 1;
const PAGE_SIZE = 50;

const pageIndicatorEl = document.getElementById('pageIndicator');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');

async function loadMessages() {
  statusEl.textContent = 'Loading...';
  console.debug('[loadMessages] page=', currentPage, 'search="' + currentSearch + '"', 'trash=', showingTrash);
  try {
    let data;
    if (showingTrash) {
      data = await window.emailApi.listTrash(currentPage, PAGE_SIZE);
    } else {
      data = await window.emailApi.listMessages(currentPage, PAGE_SIZE, currentSearch);
    }
    if (!data || typeof data !== 'object') {
      console.error('[loadMessages] Unexpected response shape:', data);
      statusEl.textContent = 'Unexpected response';
      return;
    }
    const messages = Array.isArray(data.messages) ? data.messages : [];
    console.debug('[loadMessages] received', messages.length, 'messages');
    if (currentSearch && !messages.length) {
      console.debug('[loadMessages] No matches for search term:', currentSearch);
    }
    renderList(messages);
    statusEl.textContent = `Loaded ${messages.length} messages` + (currentSearch ? ` (search="${currentSearch}")` : '');
    updatePaginationControls(messages.length);
  } catch (e) {
    let msg = 'Error loading messages';
    if (e && e.message) msg += ': ' + e.message;
    statusEl.textContent = msg;
    console.error('[loadMessages] error:', e);
  }
}

function updatePaginationControls(count) {
  pageIndicatorEl.textContent = `Page ${currentPage}`;
  prevPageBtn.disabled = currentPage === 1;
  // If we got fewer than PAGE_SIZE items, assume no next page.
  nextPageBtn.disabled = count < PAGE_SIZE;
}

function renderList(messages) {
  msgListEl.innerHTML = '';
  if (!messages.length) {
    msgListEl.innerHTML = '<div class="no-results">No results</div>';
    return;
  }
  const tokens = (currentSearch || '').split(/\s+/).filter(Boolean);
  messages.forEach(m => {
    const div = document.createElement('div');
    div.className = 'msg' + (m.hidden ? ' hidden' : '');
    const subjectHtml = highlight(m.subject || '(No Subject)', tokens);
    const fromAddrHtml = highlight(m.from_addr || '', tokens);
    const bodySnippetHtml = highlight(makeSnippet(m.body_plain || '', tokens), tokens);
    const date = formatDate(m.date_received);
    div.innerHTML = `
      <div class="row">
        <div class="left">
          <div class="subject">${subjectHtml}</div>
          <div class="from">${fromAddrHtml}</div>
          <div class="snippet">${bodySnippetHtml}</div>
        </div>
        <div class="right">${escapeHtml(date)}</div>
      </div>
    `;
    div.onclick = () => showDetail(m.id);
    msgListEl.appendChild(div);
  });
}

async function showDetail(id) {
  currentMessageId = id;
  statusEl.textContent = 'Loading message...';
  try {
    const msg = await window.emailApi.getMessage(id);
    detailSubjectEl.textContent = msg.subject || '(No Subject)';
    detailMetaEl.textContent = `${msg.from_addr} → ${msg.to_addrs || ''} | ${formatDate(msg.date_received)}`;
    detailBodyEl.innerHTML = msg.body_html_sanitized || `<pre>${escapeHtml(msg.body_plain || '')}</pre>`;
    deleteBtn.style.display = msg.hidden ? 'none' : 'inline-block';
    restoreBtn.style.display = msg.hidden ? 'inline-block' : 'none';
    detailToolbarEl.style.display = 'flex';
    statusEl.textContent = 'Message loaded';
  } catch (e) {
    statusEl.textContent = 'Message not found (maybe deleted)';
    console.error(e);
  }
}

function escapeHtml(str){
  return str.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
}

function formatDate(dateStr){
  if(!dateStr) return '';
  const d = new Date(dateStr);
  if(isNaN(d.getTime())) return dateStr;
  return d.toLocaleString(undefined, { year:'numeric', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit' });
}

async function doDelete() {
  if (!currentMessageId) return;
  statusEl.textContent = 'Deleting...';
  try {
    await window.emailApi.deleteMessage(currentMessageId);
    statusEl.textContent = 'Deleted';
    // Clear detail view
    currentMessageId = null;
    detailSubjectEl.textContent = '';
    detailMetaEl.textContent = '';
    detailBodyEl.innerHTML = '';
    detailToolbarEl.style.display = 'none';
    loadMessages();
  } catch (e) {
    statusEl.textContent = 'Delete failed';
    console.error(e);
  }
}

async function doRestore() {
  if (!currentMessageId) return;
  statusEl.textContent = 'Restoring...';
  try {
    await window.emailApi.restoreMessage(currentMessageId);
    statusEl.textContent = 'Restored';
    loadMessages();
    showDetail(currentMessageId);
  } catch (e) {
    statusEl.textContent = 'Restore failed';
    console.error(e);
  }
}

async function doSync() {
  const host = document.getElementById('imapHost').value.trim();
  const user = document.getElementById('imapUser').value.trim();
  const pass = document.getElementById('imapPass').value.trim();
  if (!host || !user || !pass) {
    statusEl.textContent = 'Enter host, username, password';
    return;
  }
  statusEl.textContent = 'Syncing...';
  try {
    const r = await window.emailApi.sync(host, user, pass);
    statusEl.textContent = `Fetched ${r.fetched} new messages`;
    loadMessages();
  } catch (e) {
    statusEl.textContent = 'Sync failed';
    console.error(e);
  }
}

function doSearch() {
  currentSearch = document.getElementById('searchBox').value.trim();
  currentPage = 1;
  loadMessages();
}

function clearSearch() {
  document.getElementById('searchBox').value = '';
  currentSearch = '';
  currentPage = 1;
  loadMessages();
}

// Event bindings

document.getElementById('syncBtn').onclick = doSync;

document.getElementById('searchBtn').onclick = doSearch;

document.getElementById('clearSearchBtn').onclick = clearSearch;

document.getElementById('trashToggle').onchange = (e) => {
  showingTrash = e.target.checked;
  currentPage = 1;
  loadMessages();
};
prevPageBtn.onclick = () => {
  if (currentPage > 1) {
    currentPage--;
    loadMessages();
  }
};

nextPageBtn.onclick = () => {
  currentPage++;
  loadMessages();
};

deleteBtn.onclick = doDelete;
restoreBtn.onclick = doRestore;

// Settings: theme + hide on blur + menu toggle
const settingsBtnEl = document.getElementById('settingsBtn');
const settingsMenuEl = document.getElementById('settingsMenu');
const settingsDarkEl = document.getElementById('settingsDark');

function applyTheme(theme) {
  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}
// Load and apply saved preferences
let savedTheme = 'light';
try {
  savedTheme = localStorage.getItem('theme') || 'light';
} catch {}
applyTheme(savedTheme);
if (settingsDarkEl) settingsDarkEl.checked = savedTheme === 'dark';

if (settingsBtnEl && settingsMenuEl) {
  settingsBtnEl.addEventListener('click', () => {
    settingsMenuEl.style.display = settingsMenuEl.style.display === 'none' || !settingsMenuEl.style.display ? 'block' : 'none';
  });
  // Hide menu when clicking outside
  document.addEventListener('click', (e) => {
    if (e.target === settingsBtnEl || settingsMenuEl.contains(e.target)) return;
    settingsMenuEl.style.display = 'none';
  });
}
if (settingsDarkEl) {
  settingsDarkEl.addEventListener('change', (e) => {
    const theme = e.target.checked ? 'dark' : 'light';
    applyTheme(theme);
    try { localStorage.setItem('theme', theme); } catch {}
  });
}
// No hide-on-blur setting anymore

// Sidebar splitter drag-to-resize + persistence
const sidebarEl = document.getElementById('sidebar');
const splitterEl = document.getElementById('splitter');
try {
  const w = parseInt(localStorage.getItem('sidebarWidthPx') || '0', 10);
  if (w && sidebarEl) sidebarEl.style.width = w + 'px';
} catch {}
if (splitterEl && sidebarEl) {
  let dragging = false;
  let startX = 0;
  let startW = 0;
  const minW = 220;
  function onMove(e) {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const maxW = Math.floor(window.innerWidth * 0.6);
    let newW = Math.max(minW, Math.min(startW + dx, maxW));
    sidebarEl.style.width = newW + 'px';
  }
  function onUp() {
    if (!dragging) return;
    dragging = false;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    try {
      const w = parseInt(getComputedStyle(sidebarEl).width, 10);
      localStorage.setItem('sidebarWidthPx', String(w));
    } catch {}
  }
  splitterEl.addEventListener('mousedown', (e) => {
    dragging = true;
    startX = e.clientX;
    startW = parseInt(getComputedStyle(sidebarEl).width, 10);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

// Highlight helpers
function highlight(text, tokens) {
  if (!text) return '';
  if (!tokens || tokens.length === 0) return escapeHtml(text);
  let out = escapeHtml(text);
  for (const t of tokens) {
    const safe = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(${safe})`, 'ig');
    out = out.replace(re, '<mark>$1</mark>');
  }
  return out;
}
function makeSnippet(bodyPlain, tokens, maxLen = 140) {
  if (!bodyPlain) return '';
  const text = (bodyPlain || '').replace(/\s+/g, ' ').trim();
  if (!tokens || tokens.length === 0) return escapeHtml(text.slice(0, maxLen));
  let idx = -1;
  for (const t of tokens) {
    const i = text.toLowerCase().indexOf(t.toLowerCase());
    if (i !== -1 && (idx === -1 || i < idx)) idx = i;
  }
  let start = 0;
  if (idx > 20) start = idx - 20;
  const snippet = text.slice(start, start + maxLen);
  const prefix = start > 0 ? '…' : '';
  const suffix = start + maxLen < text.length ? '…' : '';
  return prefix + snippet + suffix;
}

// Initial load
loadMessages();
