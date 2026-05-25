// ── Modal global ─────────────────────────────────────────────
function openModal(title, html) {
  document.getElementById('m-title').textContent = title;
  document.getElementById('m-body').innerHTML = html;
  document.getElementById('modal').classList.add('show');
}
function closeModal() {
  document.getElementById('modal').classList.remove('show');
  document.getElementById('m-body').innerHTML = '';
}

// ── Toast ─────────────────────────────────────────────────────
function showToast(msg, color = 'blue') {
  const colors = {
    green: { bg: 'var(--green-g)', border: 'var(--green)', text: 'var(--green)' },
    blue:  { bg: 'var(--blue-glow)', border: 'var(--blue)', text: 'var(--blue-lt)' },
    amber: { bg: 'var(--amber-g)', border: 'var(--amber)', text: 'var(--amber)' },
    red:   { bg: 'var(--red-g)', border: 'var(--red)', text: 'var(--red)' },
  };
  const c = colors[color] || colors.blue;
  const t = document.createElement('div');
  t.style.cssText = `position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${c.bg};border:1.5px solid ${c.border};color:${c.text};
    padding:12px 20px;border-radius:10px;font-weight:600;font-size:13px;
    box-shadow:0 4px 20px rgba(0,0,0,.3);font-family:Outfit,sans-serif;`;
  t.textContent = msg;
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
  // Modal overlay close on backdrop click
  const modal = document.getElementById('modal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
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
    if (action === 'close-sidebar') return closeSidebar();
    if (action === 'toggle-theme') return toggleTheme();
    if (action === 'close-modal') return closeModal();
  });
});
