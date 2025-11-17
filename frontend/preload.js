const { contextBridge, ipcRenderer } = require('electron');

const BACKEND_TOKEN = process.env.BACKEND_TOKEN || 'dev-token';
function resolvePort() {
  const arg = process.argv.find(a => a.startsWith('--backend-port='));
  if (process.env.ACTUAL_BACKEND_PORT) return process.env.ACTUAL_BACKEND_PORT;
  if (arg) return arg.split('=')[1];
  return '8137';
}
const BASE = `http://127.0.0.1:${resolvePort()}`;

async function apiGet(path, params = {}) {
  const url = new URL(BASE + path);
  Object.keys(params).forEach(k => url.searchParams.append(k, params[k]));
  const res = await fetch(url.toString(), { headers: { 'X-Auth-Token': BACKEND_TOKEN } });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path, params = {}) {
  const url = new URL(BASE + path);
  Object.keys(params).forEach(k => url.searchParams.append(k, params[k]));
  const res = await fetch(url.toString(), { method: 'POST', headers: { 'X-Auth-Token': BACKEND_TOKEN } });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

contextBridge.exposeInMainWorld('emailApi', {
  health: () => apiGet('/health'),
  sync: (host, username, password, port = 993) => apiPost('/sync', { host, port, username, password }),
  listMessages: (page = 1, page_size = 50, search = '') => apiGet('/messages', { page, page_size, ...(search ? { search } : {}) }),
  getMessage: (id) => apiGet(`/messages/${id}`),
  deleteMessage: (id) => apiPost(`/messages/${id}/delete`),
  restoreMessage: (id) => apiPost(`/messages/${id}/restore`),
  listTrash: (page = 1, page_size = 50) => apiGet('/trash', { page, page_size }),
  listAccounts: () => apiGet('/accounts'),
  createAccount: (email_address, imap_host, imap_port, username, password) => fetch(`${BASE}/accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': BACKEND_TOKEN },
    body: JSON.stringify({ email_address, imap_host, imap_port, username, password })
  }).then(r => { if(!r.ok) throw new Error('Create account failed'); return r.json(); }),
  syncAccount: (account_id) => apiPost(`/accounts/${account_id}/sync`),
  rotatePassword: (account_id, password) => fetch(`${BASE}/accounts/${account_id}/password`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': BACKEND_TOKEN },
    body: JSON.stringify({ password })
  }).then(r => { if(!r.ok) throw new Error('Rotate password failed'); return r.json(); }),
  gmailAuthUrl: () => apiGet('/gmail/auth_url'),
  gmailSync: (account_id) => apiPost('/gmail/sync', { account_id }),
  deleteAccount: (account_id) => fetch(`${BASE}/accounts/${account_id}`, {
    method: 'DELETE',
    headers: { 'X-Auth-Token': BACKEND_TOKEN }
  }).then(r => { if(!r.ok) throw new Error('Delete failed'); return r.json(); }),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
});

// No app-level IPC exposed currently
