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
  messages.forEach(m => {
    const div = document.createElement('div');
    div.className = 'msg' + (m.hidden ? ' hidden' : '');
    div.textContent = `${m.subject || '(No Subject)'} | ${m.from_addr} | ${formatDate(m.date_received)}`;
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

// Initial load
loadMessages();
