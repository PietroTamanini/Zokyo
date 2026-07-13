/**
 * api.js — camada fetch para rotas /api/*
 */
async function apiFetch(method, path, body) {
  const opts = {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
  };
  if (!['GET','HEAD','OPTIONS'].includes(method)) {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) opts.headers['X-CSRFToken'] = meta.content;
  }
  if (body) opts.body = JSON.stringify(body);
  try {
    const r    = await fetch(path, opts);
    const contentType = r.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await r.json().catch(() => null) : null;
    if (!r.ok) {
      if (r.status === 401) {
        if (typeof showToast === 'function') showToast('Sessão expirada. Faça login novamente.', 'amber');
        if (location.pathname !== '/login') location.href = '/login';
        return null;
      }
      if (r.status === 403) {
        if (typeof showToast === 'function') showToast('Acesso negado.', 'red');
        return null;
      }
      if (r.status === 429) {
        const retry = data?.retry_after ? ` Tente novamente em ${data.retry_after}s.` : '';
        if (typeof showToast === 'function') showToast(`Muitas requisições.${retry}`, 'amber');
        return null;
      }
      const requestId = r.headers.get('X-Request-ID');
      const suffix = requestId && r.status >= 500 ? ` Referência: ${requestId}.` : '';
      if (typeof showToast === 'function') showToast(`${data?.erro || 'Não foi possível concluir a operação.'}${suffix}`, 'red');
      return null;
    }
    return data;
  } catch {
    if (typeof showToast === 'function') showToast('Erro de conexão com o servidor.', 'red');
    return null;
  }
}
const apiGet  = p     => apiFetch('GET',    p);
const apiPost = (p,b) => apiFetch('POST',   p, b);
const apiPut  = (p,b) => apiFetch('PUT',    p, b);
const apiDel  = p     => apiFetch('DELETE', p);
