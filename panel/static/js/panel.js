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
  if (tbody) tbody.innerHTML = `<tr><td colspan="99" class="table-state" style="color:var(--red)">${msg}</td></tr>`;
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
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Strip mIRC/IRC formatting codes before display
//  bold,  color (+ optional NN,NN),  reset,
//  monospace,  reverse,  italic,  strikethrough,  underline
function stripIrc(str) {
  return String(str ?? '')
    .replace(/\d{1,2}(?:,\d{1,2})?/g, '') // color codes with args
    .replace(/[]/g, ''); // remaining control chars
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
  confirm, fmtTime, fmtDate, fmtDuration, esc, stripIrc,
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
