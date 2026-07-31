// ── Modal global ─────────────────────────────────────────────
let modalReturnFocus = null;

function modalFocusable() {
  return [...document.querySelectorAll('#modal .modal-box a[href], #modal .modal-box button:not([disabled]), #modal .modal-box input:not([disabled]), #modal .modal-box select:not([disabled]), #modal .modal-box textarea:not([disabled]), #modal .modal-box [tabindex]:not([tabindex="-1"])')]
    .filter(el => !el.hidden && el.offsetParent !== null);
}

function openModal(title, html) {
  modalReturnFocus = document.activeElement;
  document.getElementById('m-title').textContent = title;
  document.getElementById('m-body').innerHTML = html;
  const modal = document.getElementById('modal');
  modal.inert = false;
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('body-lock');
  requestAnimationFrame(() => {
    const primaryField = modal.querySelector('#m-body input:not([type="hidden"]), #m-body select, #m-body textarea');
    (primaryField || modalFocusable()[0] || modal.querySelector('.modal-box')).focus();
  });
}
function closeModal() {
  const modal = document.getElementById('modal');
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  modal.inert = true;
  document.getElementById('m-body').innerHTML = '';
  document.body.classList.remove('body-lock');
  if (modalReturnFocus?.isConnected) modalReturnFocus.focus();
  modalReturnFocus = null;
}

// ── Toast ─────────────────────────────────────────────────────
function showToast(msg, color = 'blue') {
  const t = document.createElement('div');
  const allowed = ['green', 'blue', 'amber', 'red'];
  t.className = `toast toast-${allowed.includes(color) ?color : 'blue'}`;
  t.textContent = msg;
  t.setAttribute('role', color === 'red' ?'alert' : 'status');
  t.setAttribute('aria-live', color === 'red' ?'assertive' : 'polite');
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ── API helper ────────────────────────────────────────────────
async function apiCall(method, url, body) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const opts = {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  const d = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data: d };
}

// ── CSP-safe event wiring (no inline handlers) ─────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.table-wrap').forEach((region) => {
    region.tabIndex = 0;
    if (!region.hasAttribute('aria-label')) region.setAttribute('aria-label', 'Tabela com rolagem horizontal');
  });

  // Associate legacy visual labels with controls and name standalone filters.
  document.querySelectorAll('input:not([type="hidden"]), select, textarea').forEach((control, index) => {
    if (control.labels?.length || control.hasAttribute('aria-label') || control.hasAttribute('aria-labelledby')) return;

    const container = control.closest('.form-group, .field, .filter-group, .input-group') || control.parentElement;
    const visualLabel = container?.querySelector('label');
    if (visualLabel) {
      if (!control.id) control.id = `field-${index}`;
      visualLabel.htmlFor = control.id;
      return;
    }

    const optionText = control.tagName === 'SELECT'
      ?control.querySelector('option')?.textContent?.trim()
      : '';
    const fieldName = (control.name || control.placeholder || optionText || 'Campo')
      .replace(/[_-]+/g, ' ')
      .trim();
    control.setAttribute('aria-label', fieldName.charAt(0).toUpperCase() + fieldName.slice(1));
  });

  // Modal overlay close on backdrop click
  const modal = document.getElementById('modal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
    modal.addEventListener('keydown', (e) => {
      if (e.key !== 'Tab') return;
      const focusable = modalFocusable();
      if (!focusable.length) return e.preventDefault();
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
  }

  // Confirmations for destructive actions
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      const msg = form.getAttribute('data-confirm') || 'Confirmar ação?';
      if (!confirm(msg)) e.preventDefault();
    });
  });

  // Auto-submit on change
  document.querySelectorAll('[data-auto-submit]').forEach((el) => {
    el.addEventListener('change', () => {
      const form = el.closest('form');
      if (form) form.submit();
    });
  });

  // Generic navigation (rows/cards)
  document.addEventListener('click', (e) => {
    const blocker = e.target.closest('[data-stop]');
    if (blocker) return;
    const nav = e.target.closest('[data-href]');
    if (nav) window.location.href = nav.getAttribute('data-href');
  });

  // Global actions
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const action = el.getAttribute('data-action');
    if (action === 'open-sidebar') return openSidebar();
    if (action === 'toggle-sidebar') return toggleSidebar();
    if (action === 'close-sidebar') return closeSidebar();
    if (action === 'toggle-theme') return toggleTheme();
    if (action === 'close-modal') return closeModal();
    if (action === 'history-back') return history.length > 1 ?history.back() : (location.href = '/');
  });
});
