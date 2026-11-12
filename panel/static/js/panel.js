/* panel.js — UnrealIRCd Admin Panel */
'use strict';

// ============================================================
// Theme
// ============================================================
const THEME_KEY = 'unrealircd-theme';

function getTheme() {
  return localStorage.getItem(THEME_KEY) || 'light';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
}

function toggleTheme() {
  applyTheme(getTheme() === 'light' ? 'dark' : 'light');
}

// Apply immediately (before paint) — prevents flash
applyTheme(getTheme());

// ============================================================
// Sidebar (mobile)
// ============================================================
function initSidebar() {
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('sidebarOverlay');
  const hamburger= document.getElementById('hamburger');
  const closeBtn = document.getElementById('sidebarClose');
  if (!sidebar) return;

  function open() {
    sidebar.classList.add('open');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function close() {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  hamburger?.addEventListener('click', open);
  closeBtn?.addEventListener('click', close);
  overlay?.addEventListener('click', close);

  // Close on nav click (mobile)
  sidebar.querySelectorAll('.nav-item').forEach(a => {
    a.addEventListener('click', () => {
      if (window.innerWidth <= 768) close();
    });
  });
}

// ============================================================
// Toast notifications
// ============================================================
let toastContainer;

function getToastContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);
  }
  return toastContainer;
}

function toast(msg, type = 'ok', duration = 3000) {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  getToastContainer().appendChild(el);
  setTimeout(() => {
    el.classList.add('toast-out');
    setTimeout(() => el.remove(), 220);
  }, duration);
}

// ============================================================
// API helpers
// ============================================================
async function api(path, opts = {}) {
  const defaults = {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  const res = await fetch(path, { ...defaults, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiGet(path) { return api(path); }
async function apiPost(path, body) {
  return api(path, { method: 'POST', body: JSON.stringify(body) });
}
async function apiDelete(path) {
  return api(path, { method: 'DELETE' });
}

// ============================================================
// Table helpers
// ============================================================

/**
 * Render a table.
 * @param {string} tbodyId
 * @param {Array}  rows     — array of <tr> HTML strings
 * @param {string} emptyMsg
 */
function renderTable(tbodyId, rows, emptyMsg = 'No data') {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  if (!rows || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="99" class="table-state">${emptyMsg}</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.join('');
}

function tableLoadingState(tbodyId, msg = '⟳ loading…') {
  const tbody = document.getElementById(tbodyId);
  if (tbody) tbody.innerHTML = `<tr><td colspan="99" class="table-state">${msg}</td></tr>`;
}

function tableErrorState(tbodyId, msg) {
  const tbody = document.getElementById(tbodyId);
  if (tbody) tbody.innerHTML = `<tr><td colspan="99" class="table-state" style="color:var(--red)">${esc(msg)}</td></tr>`;
}

/**
 * Wire up a search input to filter table rows by text content.
 */
function initTableSearch(inputId, tbodyId) {
  const input = document.getElementById(inputId);
  const tbody = document.getElementById(tbodyId);
  if (!input || !tbody) return;
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    tbody.querySelectorAll('tr[data-search]').forEach(tr => {
      const text = tr.dataset.search.toLowerCase();
      tr.style.display = (!q || text.includes(q)) ? '' : 'none';
    });
  });
}

// ============================================================
// Sortable table headers
// ============================================================
// Usage: initSortableTable('tbodyId', [colIndex, ...])
// Columns must have data-col="N" on <th> elements.
// Rows need data-sort-N="value" attributes for sortable cols,
// or falls back to cell text content.
function initSortableTable(tbodyId) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const table = tbody.closest('table');
  if (!table) return;
  const state = {}; // col -> 'asc'|'desc'

  table.querySelectorAll('th[data-sort-col]').forEach(th => {
    th.style.cursor = 'pointer';
    th.style.userSelect = 'none';
    th.addEventListener('click', () => {
      const col = parseInt(th.dataset.sortCol, 10);
      const dir = state[col] === 'asc' ? 'desc' : 'asc';
      state[col] = dir;

      // Update header arrows
      table.querySelectorAll('th[data-sort-col]').forEach(h => {
        h.dataset.sortDir = h === th ? dir : '';
      });

      // Sort rows
      const rows = [...tbody.querySelectorAll('tr[data-search]')];
      rows.sort((a, b) => {
        const av = a.dataset['sort' + col] ?? a.cells[col]?.textContent.trim() ?? '';
        const bv = b.dataset['sort' + col] ?? b.cells[col]?.textContent.trim() ?? '';
        const an = parseFloat(av), bn = parseFloat(bv);
        const cmp = (!isNaN(an) && !isNaN(bn))
          ? an - bn
          : av.localeCompare(bv, undefined, { sensitivity: 'base' });
        return dir === 'asc' ? cmp : -cmp;
      });
      rows.forEach(r => tbody.appendChild(r));
    });
  });
}

// ============================================================
// Modal helpers
// ============================================================
function openModal(id) {
  document.getElementById(id)?.classList.add('open');
}
function closeModal(id) {
  document.getElementById(id)?.classList.remove('open');
}

function initModals() {
  // Close on backdrop click
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', e => {
      if (e.target === backdrop) backdrop.classList.remove('open');
    });
  });
  // Close buttons
  document.querySelectorAll('.modal-close, [data-modal-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.modal-backdrop')?.classList.remove('open');
    });
  });
  // Escape key
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop.open').forEach(m => m.classList.remove('open'));
    }
  });
}

// ============================================================
// Confirm dialog (reusable)
// ============================================================
function confirm(title, body, onConfirm, danger = true) {
  // Reuse or create a shared confirm modal
  let modal = document.getElementById('_confirmModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = '_confirmModal';
    modal.className = 'modal-backdrop';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-header">
          <span class="modal-title" id="_confirmTitle"></span>
          <button class="modal-close">✕</button>
        </div>
        <div class="modal-body" id="_confirmBody"></div>
        <div class="modal-footer">
          <button class="btn btn-ghost" id="_confirmCancel">Cancel</button>
          <button class="btn" id="_confirmOk">Confirm</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    initModals();
  }

  document.getElementById('_confirmTitle').textContent = title;
  document.getElementById('_confirmBody').textContent = body;
  const ok = document.getElementById('_confirmOk');
  ok.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;
  ok.textContent = 'Confirm';

  const newOk = ok.cloneNode(true); // remove old listeners
  ok.replaceWith(newOk);
  newOk.addEventListener('click', () => {
    modal.classList.remove('open');
    onConfirm();
  });

  document.getElementById('_confirmCancel').onclick = () => modal.classList.remove('open');
  modal.querySelector('.modal-close').onclick = () => modal.classList.remove('open');
  modal.classList.add('open');
}

// ============================================================
// Format helpers
// ============================================================
function fmtTime(ts) {
  if (!ts) return '—';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtDate(ts) {
  if (!ts) return '—';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtDuration(secs) {
  if (!secs) return '0s';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// A value as a JS string literal for an inline handler, e.g.
//   onclick="openUser(${Panel.jsArg(nick)})"
// esc() alone is not enough there: the browser decodes the attribute before
// parsing the JS, so quotes and backslashes in the value (nicks like
// foo\bar, regex spamfilters, channel names with ') would break out of or
// mangle a hand-quoted '...' string.
// Shown instead of "remove" for entries from unrealircd.conf (set_in_config):
// JSON-RPC cannot delete those, they have to be removed from the config.
const CONFIG_BADGE = '<span class="badge badge-muted" title="Set in the configuration file; remove it there and rehash">config</span>';

function jsArg(value) {
  return esc(JSON.stringify(String(value ?? '')));
}

// Rows for a details drawer (.detail-grid): [[label, value, opts], ...].
// Rows whose value is null/undefined/'' are skipped. Values are escaped unless
// opts.html; opts.irc renders IRC colours/bold; opts.prose shows wrapping
// sans-serif text (reasons, descriptions).
function detailRows(rows) {
  return rows
    .filter(r => r && r[1] !== undefined && r[1] !== null && r[1] !== '')
    .map(([key, value, opts = {}]) =>
      `<span class="detail-key">${esc(key)}</span>` +
      `<span class="detail-val${opts.prose ? ' prose' : ''}">${opts.html ? value : opts.irc ? ircToHtml(value) : esc(value)}</span>`)
    .join('');
}

// "in 3d 4h" / "2h ago" style relative time for an ISO timestamp
function fmtRelative(ts) {
  if (!ts) return '';
  const secs = Math.round((new Date(ts).getTime() - Date.now()) / 1000);
  const a = Math.abs(secs), days = Math.floor(a / 86400);
  const d = days > 0 ? `${days}d ${Math.floor((a % 86400) / 3600)}h` : fmtDuration(a);
  return secs >= 0 ? 'in ' + d : d + ' ago';
}

// ── IRC formatting (mIRC codes) ─────────────────────────────────────────
// \x02 bold, \x1D italic, \x1F underline, \x1E strikethrough, \x11 monospace,
// \x16 reverse, \x0F reset, \x03NN[,NN] colour, \x04RRGGBB[,RRGGBB] hex colour.
const IRC_PALETTE = (
  'FFFFFF 000000 00007F 009300 FF0000 7F0000 9C009C FC7F00 FFFF00 00FC00 009393 00FFFF 0000FC FF00FF 7F7F7F D2D2D2 ' +
  '470000 472100 474700 324700 004700 00472C 004747 002747 000047 2E0047 470047 47002A ' +
  '740000 743A00 747400 517400 007400 007449 007474 004074 000074 4B0074 740074 740045 ' +
  'B50000 B56300 B5B500 7DB500 00B500 00B571 00B5B5 0063B5 0000B5 7500B5 B500B5 B5006B ' +
  'FF0000 FF8C00 FFFF00 B2FF00 00FF00 00FFA0 00FFFF 008CFF 0000FF A500FF FF00FF FF0098 ' +
  'FF5959 FFB459 FFFF71 CFFF60 6FFF6F 65FFC9 6DFFFF 59B4FF 5959FF C459FF FF66FF FF59BC ' +
  'FF9C9C FFD39C FFFF9C E2FF9C 9CFF9C 9CFFDB 9CFFFF 9CD3FF 9C9CFF DC9CFF FF9CFF FF94D3 ' +
  '000000 131313 282828 363636 4D4D4D 656565 818181 9F9F9F BCBCBC E2E2E2 FFFFFF'
).split(' ').map(h => '#' + h);   // 0-98; 99 means "default colour"

const IRC_COLOR_RE = /^\x03(?:(\d{1,2})(?:,(\d{1,2}))?)?/;
const IRC_HEX_RE   = /^\x04(?:([0-9a-fA-F]{6})(?:,([0-9a-fA-F]{6}))?)?/;

function ircColor(n) {
  if (n === undefined) return undefined;
  const i = parseInt(n, 10);
  return i >= 0 && i < IRC_PALETTE.length ? IRC_PALETTE[i] : null;  // null = default
}

// Plain text with all formatting codes removed (titles, search, dialogs)
function stripIrc(str) {
  return String(str ?? '')
    .replace(/\x03(\d{1,2}(,\d{1,2})?)?/g, '')
    .replace(/\x04([0-9a-fA-F]{6}(,[0-9a-fA-F]{6})?)?/g, '')
    .replace(/[\x00-\x08\x0B-\x1F\x7F]/g, '');
}

// Escaped HTML with the formatting rendered as <span> styles
function ircToHtml(str) {
  const s = String(str ?? '');
  const st = { b: false, i: false, u: false, x: false, m: false, r: false, fg: null, bg: null };
  let out = '', run = '';
  const flush = () => {
    if (!run) return;
    let fg = st.fg, bg = st.bg;
    if (st.r) { [fg, bg] = [bg || 'var(--surface)', fg || 'var(--text)']; }
    const css = [];
    if (st.b) css.push('font-weight:600');
    if (st.i) css.push('font-style:italic');
    const deco = [st.u && 'underline', st.x && 'line-through'].filter(Boolean);
    if (deco.length) css.push('text-decoration:' + deco.join(' '));
    if (st.m) css.push("font-family:'IBM Plex Mono',monospace");
    if (fg) css.push('color:' + fg);
    if (bg) css.push('background:' + bg + ';border-radius:2px');
    out += css.length ? `<span style="${css.join(';')}">${esc(run)}</span>` : esc(run);
    run = '';
  };
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    const code = c.charCodeAt(0);
    if (code >= 0x20 && code !== 0x7F) { run += c; continue; }
    flush();
    switch (c) {
      case '\x02': st.b = !st.b; break;
      case '\x1D': st.i = !st.i; break;
      case '\x1F': st.u = !st.u; break;
      case '\x1E': st.x = !st.x; break;
      case '\x11': st.m = !st.m; break;
      case '\x16': st.r = !st.r; break;
      case '\x0F': Object.assign(st, { b: false, i: false, u: false, x: false, m: false, r: false, fg: null, bg: null }); break;
      case '\x03': {
        const m = s.slice(i).match(IRC_COLOR_RE);
        if (m[1] === undefined) { st.fg = st.bg = null; }            // bare \x03 resets colours
        else { st.fg = ircColor(m[1]); if (m[2] !== undefined) st.bg = ircColor(m[2]); }
        i += m[0].length - 1; break;
      }
      case '\x04': {
        const m = s.slice(i).match(IRC_HEX_RE);
        if (m[1] === undefined) { st.fg = st.bg = null; }
        else { st.fg = '#' + m[1]; if (m[2] !== undefined) st.bg = '#' + m[2]; }
        i += m[0].length - 1; break;
      }
      default: break;   // other control characters are dropped
    }
  }
  flush();
  return out;
}

// ============================================================
// Init
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  applyTheme(getTheme());

  // Wire theme toggles (sidebar + mobile topbar)
  document.querySelectorAll('.theme-toggle').forEach(btn => {
    btn.addEventListener('click', toggleTheme);
  });

  initSidebar();
  initModals();
});

// Expose globals for page scripts
window.Panel = {
  api, apiGet, apiPost, apiDelete,
  toast, openModal, closeModal,
  renderTable, tableLoadingState, tableErrorState, initTableSearch, initSortableTable,
  confirm, fmtTime, fmtDate, fmtDuration, fmtRelative, detailRows, esc, jsArg, stripIrc, ircToHtml, CONFIG_BADGE,
};

// ============================================================
// Drawer helpers
// ============================================================
function openDrawer(id) {
  document.getElementById(id + 'Backdrop')?.classList.add('open');
  document.getElementById(id)?.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeDrawer(id) {
  document.getElementById(id + 'Backdrop')?.classList.remove('open');
  document.getElementById(id)?.classList.remove('open');
  document.body.style.overflow = '';
}

function initDrawers() {
  document.querySelectorAll('.drawer-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', () => {
      const id = backdrop.id.replace('Backdrop', '');
      closeDrawer(id);
    });
  });
  document.querySelectorAll('.drawer-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const drawer = btn.closest('.drawer');
      if (drawer) closeDrawer(drawer.id);
    });
  });
}

// ============================================================
// Tab helpers
// ============================================================
function initTabs(containerSelector) {
  document.querySelectorAll(containerSelector || '.tabs').forEach(tabGroup => {
    tabGroup.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        // Tab buttons live in .tabs; panels live in .drawer-body (sibling of .tabs)
        // Walk up to the nearest .drawer-body or .tab-container, else fall back to grandparent
        const panelScope = tabGroup.closest('.drawer-body') || tabGroup.closest('.tab-container') || tabGroup.parentElement;
        tabGroup.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        panelScope.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        panelScope.querySelector('#' + target)?.classList.add('active');
      });
    });
  });
}

// Password show/hide toggle
// Wraps every input[type=password] inside a .pw-wrap div and injects an eye button.
// Call once after DOM ready; safe to call again (skips already-wrapped inputs).
function initPasswordToggles(root) {
  (root || document).querySelectorAll('input[type=password]').forEach(input => {
    if (input.closest('.pw-wrap')) return; // already wrapped
    const wrap = document.createElement('div');
    wrap.className = 'pw-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pw-toggle';
    btn.setAttribute('aria-label', 'Toggle password visibility');
    btn.innerHTML = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" xmlns="http://www.w3.org/2000/svg" class="pw-eye pw-eye-show"><path d="M1 10s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"/><circle cx="10" cy="10" r="2.5"/></svg><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" xmlns="http://www.w3.org/2000/svg" class="pw-eye pw-eye-hide" style="display:none"><path d="M1 10s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"/><circle cx="10" cy="10" r="2.5"/><line x1="3" y1="3" x2="17" y2="17"/></svg>';
    wrap.appendChild(btn);
    btn.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.querySelector('.pw-eye-show').style.display = show ? 'none' : '';
      btn.querySelector('.pw-eye-hide').style.display = show ? '' : 'none';
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    });
  });
}

// Expose new helpers
Object.assign(window.Panel, { openDrawer, closeDrawer, initDrawers, initTabs, initPasswordToggles });

document.addEventListener('DOMContentLoaded', () => {
  initDrawers();
  initPasswordToggles();
});
