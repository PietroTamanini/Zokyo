const dropdown = document.getElementById('cliente-dropdown');
const input = document.getElementById('cliente-busca');
const hiddenId = document.getElementById('cliente_id');
const partDropdown = document.getElementById('peca-dropdown');
const partInput = document.getElementById('os-peca-busca');
const partHiddenId = document.getElementById('os-peca-id');
const clienteCache = new Map();
const pecaCache = new Map();
let clienteTimer = null;
let pecaTimer = null;

function _soDigitos(v) { return (v || '').replace(/\D/g, ''); }
function _formatDoc(c) {
  const doc = c?.documento || c?.cpf || c?.cnpj || '';
  return typeof formatarCpfCnpj === 'function' ?formatarCpfCnpj(doc) : doc;
}
function _safe(v) {
  return String(v || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function clienteMatches(c, q, qDigits) {
  const nomeOk = (c.nome || '').toLowerCase().includes(q);
  const telOk = qDigits.length >= 2 && (c.telefone || '').includes(qDigits);
  const cpfOk = qDigits.length >= 2 && (c.cpf || '').includes(qDigits);
  const cnpjOk = qDigits.length >= 2 && (c.cnpj || '').includes(qDigits);
  return nomeOk || telOk || cpfOk || cnpjOk;
}

function pecaMatches(p, q) {
  const text = `${p.nome || ''} ${p.codigo || ''}`.toLowerCase();
  return text.includes(q);
}

function selecionarPeca(p) {
  if (!partHiddenId || !partInput) return;
  partHiddenId.value = p.id;
  partInput.value = `${p.nome || ''}${p.codigo ?' - ' + p.codigo : ''}`;
  if (partDropdown) partDropdown.classList.remove('show');
  const price = document.getElementById('os-peca-vlr');
  if (price) price.value = parseFloat(p.preco ?? p.preco_venda ?? 0).toFixed(2);
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!response.ok) return [];
  return await response.json();
}

async function buscarClientes(q, qDigits) {
  const key = `${q}|${qDigits}`;
  if (clienteCache.has(key)) return clienteCache.get(key);
  const params = new URLSearchParams({ q: q || qDigits, limit: '8' });
  const items = await fetchJson(`/api/clientes?${params.toString()}`);
  clienteCache.set(key, items);
  return items;
}

async function buscarPecas(q) {
  if (pecaCache.has(q)) return pecaCache.get(q);
  const params = new URLSearchParams({ q, limit: '10' });
  const items = await fetchJson(`/api/pecas?${params.toString()}`);
  pecaCache.set(q, items);
  return items;
}

document.querySelectorAll('[data-other-select]').forEach((select) => {
  const target = document.querySelector(select.dataset.otherSelect);
  const otherInput = target?.querySelector('input');
  const sync = () => {
    const show = select.value === 'Outros';
    target?.classList.toggle('is-hidden', !show);
    if (otherInput) otherInput.required = show;
    if (!show && otherInput) otherInput.value = '';
  };
  select.addEventListener('change', sync);
  sync();
});

if (input) {
  input.addEventListener('input', function () {
    const q = this.value.trim().toLowerCase();
    const qDigits = _soDigitos(q);
    clearTimeout(clienteTimer);
    if (q.length < 2 && qDigits.length < 2) {
      dropdown.classList.remove('show');
      return;
    }

    clienteTimer = setTimeout(async () => {
      const remote = await buscarClientes(q, qDigits);
      const base = remote.length ?remote : (CLIENTES_DATA || []);
      const matches = base.filter(c => clienteMatches(c, q, qDigits));
      if (!matches.length) {
        dropdown.classList.remove('show');
        return;
      }

      dropdown.innerHTML = matches.slice(0, 8).map(c => {
        const docFmt = _formatDoc(c);
        return `
        <div data-action="os-cliente-select" data-id="${c.id}"
             data-nome="${encodeURIComponent(c.nome || '')}"
             data-tel="${encodeURIComponent(c.telefone || '')}"
             data-doc="${encodeURIComponent(docFmt)}"
             class="dropdown-result">
          <strong>${_safe(c.nome)}</strong>
          <span class="dropdown-meta">
            ${_safe(c.telefone)} ${docFmt ?' - ' + _safe(docFmt) : ''}
          </span>
        </div>`;
      }).join('');
      dropdown.classList.add('show');
    }, 180);
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#cliente-busca') && !e.target.closest('#cliente-dropdown')) {
      dropdown.classList.remove('show');
    }
  });
}

if (partInput && partDropdown) {
  partInput.addEventListener('input', function () {
    const q = this.value.trim().toLowerCase();
    clearTimeout(pecaTimer);
    if (partHiddenId) partHiddenId.value = '';
    if (q.length < 2) {
      partDropdown.classList.remove('show');
      return;
    }

    pecaTimer = setTimeout(async () => {
      const remote = await buscarPecas(q);
      const base = remote.length ?remote : (PECAS_DATA || []);
      const matches = base.filter(p => pecaMatches(p, q));
      if (!matches.length) {
        partDropdown.innerHTML = '<div class="dropdown-result dropdown-empty">Nenhuma peca encontrada</div>';
        partDropdown.classList.add('show');
        return;
      }

      partDropdown.innerHTML = matches.slice(0, 10).map(p => `
      <div data-action="os-peca-select" data-id="${p.id}" class="dropdown-result">
        <strong>${_safe(p.nome)}</strong>
        <span class="dropdown-meta">
          ${p.codigo ?_safe(p.codigo) + ' - ' : ''}Estoque: ${_safe(p.quantidade)} - R$ ${parseFloat(p.preco ?? p.preco_venda ?? 0).toFixed(2).replace('.', ',')}
        </span>
      </div>`).join('');
      partDropdown.classList.add('show');
    }, 180);
    return;

    const matches = (PECAS_DATA || []).filter(p => pecaMatches(p, q));
    if (!matches.length) {
      partDropdown.innerHTML = '<div class="dropdown-result dropdown-empty">Nenhuma peça encontrada</div>';
      partDropdown.classList.add('show');
      return;
    }

    partDropdown.innerHTML = matches.slice(0, 10).map(p => `
      <div data-action="os-peca-select" data-id="${p.id}" class="dropdown-result">
        <strong>${_safe(p.nome)}</strong>
        <span class="dropdown-meta">
          ${p.codigo ?_safe(p.codigo) + ' - ' : ''}Estoque: ${_safe(p.quantidade)} - R$ ${parseFloat(p.preco || 0).toFixed(2).replace('.', ',')}
        </span>
      </div>`).join('');
    partDropdown.classList.add('show');
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#os-peca-busca') && !e.target.closest('#peca-dropdown')) {
      partDropdown.classList.remove('show');
    }
  });
}

function selecionarCliente(id, nome, tel, doc) {
  hiddenId.value = id;
  input.value = nome;
  dropdown.classList.remove('show');
  document.getElementById('cliente-card').classList.remove('is-hidden');
  document.getElementById('cliente-info').innerHTML =
    `<strong>${_safe(nome)}</strong> - ${_safe(tel || '-')} - <span class="mono-inline">${_safe(doc || '')}</span>`;
}

function trocarCliente() {
  hiddenId.value = '';
  input.value = '';
  document.getElementById('cliente-card').classList.add('is-hidden');
  input.focus();
}

function preencherClienteSelecionadoInicial() {
  if (!hiddenId?.value || input?.value) return;
  const c = (CLIENTES_DATA || []).find(item => String(item.id) === String(hiddenId.value));
  if (c) selecionarCliente(c.id, c.nome, c.telefone || '', _formatDoc(c));
}

function quickClientHtml() {
  return `
    <form id="quick-client-form" data-validate>
      <div class="form-row fr2">
        <div class="form-group">
          <label>Nome *</label>
          <input type="text" name="nome" class="validate-required" data-min="2" required>
        </div>
        <div class="form-group">
          <label>CPF/CNPJ</label>
          <input type="text" name="cpf_cnpj" class="mask-cpf-cnpj validate-cpf-cnpj" placeholder="CPF ou CNPJ">
        </div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>Telefone</label>
          <input type="text" name="telefone" class="mask-phone validate-phone" placeholder="(00) 00000-0000">
        </div>
        <div class="form-group">
          <label>CEP</label>
          <input type="text" name="cep" class="mask-cep validate-cep"
                 data-viacep data-fill-logradouro="[name=endereco]"
                 data-fill-cidade="[name=cidade]" data-fill-uf="[name=uf]">
        </div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Endereço</label><input type="text" name="endereco"></div>
        <div class="form-group"><label>Número da casa</label><input type="text" name="numero_casa"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Cidade</label><input type="text" name="cidade"></div>
        <div class="form-group"><label>UF</label><input type="text" name="uf" maxlength="2"></div>
      </div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="button" class="btn btn-primary" data-action="quick-client-save">Criar cliente</button>
      </div>
    </form>`;
}

function quickPayload(form) {
  return {
    nome: form.elements.nome?.value || '',
    cpf_cnpj: form.elements.cpf_cnpj?.value || '',
    telefone: form.elements.telefone?.value || '',
    cep: form.elements.cep?.value || '',
    endereco: form.elements.endereco?.value || '',
    numero_casa: form.elements.numero_casa?.value || '',
    cidade: form.elements.cidade?.value || '',
    uf: form.elements.uf?.value || '',
  };
}

function quickError(form, field, message) {
  const name = field === 'cpf' || field === 'cnpj' || field === 'documento' ?'cpf_cnpj' : field;
  const inputEl = form.elements[name] || form.elements.nome;
  inputEl.classList.add('input-error');
  let hint = inputEl.parentElement.querySelector('.field-error');
  if (!hint) {
    hint = document.createElement('span');
    hint.className = 'field-error';
    inputEl.parentElement.appendChild(hint);
  }
  hint.textContent = message;
  hint.classList.remove('hidden');
  inputEl.focus();
}

async function salvarClienteRapido() {
  const form = document.getElementById('quick-client-form');
  if (!form) return;
  form.querySelectorAll('.field-error').forEach(e => e.remove());
  form.querySelectorAll('.input-error').forEach(e => e.classList.remove('input-error'));
  if (window.DJValidators && !DJValidators.validate(form)) return;

  const r = await apiCall('POST', '/api/clientes/quick-create', quickPayload(form));
  if (!r.ok || r.data?.success === false) {
    const data = r.data || {};
    quickError(form, data.field || 'nome', data.message || data.erro || 'Não foi possível criar o cliente.');
    return;
  }

  const c = r.data.cliente;
  CLIENTES_DATA.push(c);
  closeModal();
  selecionarCliente(c.id, c.nome, c.telefone || '', c.documento || _formatDoc(c));
  showToast('Cliente criado e selecionado.', 'green');
}

function calcTotal() {
  const mo = parseFloat(document.getElementById('f-mo')?.value || 0);
  const vp = parseFloat(document.getElementById('f-vp')?.value || 0);
  const dc = parseFloat(document.getElementById('f-dc')?.value || 0);
  const tot = Math.max(0, mo + vp - dc);
  const el = document.getElementById('total-display');
  if (el) el.textContent = 'R$ ' + tot.toFixed(2).replace('.', ',').replace(/(\d)(?=(\d{3})+,)/g, '$1.');
}

async function adicionarPecaOS(osId) {
  const pid = document.getElementById('os-peca-id')?.value;
  const qtd = parseInt(document.getElementById('os-peca-qtd')?.value || 1);
  const vlr = parseFloat(document.getElementById('os-peca-vlr')?.value || 0);
  const link = document.getElementById('os-peca-link')?.value?.trim() || '';
  if (!pid) { showToast('Selecione uma peça', 'amber'); return; }
  const r = await apiCall('POST', `/api/os/${osId}/pecas`, {
    peca_id: parseInt(pid),
    quantidade: qtd,
    valor_unitario: vlr,
    link_compra: link
  });
  if (r.ok) location.reload();
  else showToast(r.data.erro || 'Erro ao adicionar peça', 'red');
}

async function removerPecaOS(osId, pecaId) {
  if (!confirm('Remover esta peça da OS?')) return;
  const r = await apiCall('DELETE', `/api/os/${osId}/pecas/${pecaId}`);
  if (r.ok) location.reload();
  else showToast(r.data.erro || 'Erro ao remover', 'red');
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'os-cliente-trocar') return trocarCliente();
  if (action === 'quick-client-open') return openModal('Cliente rapido', quickClientHtml());
  if (action === 'quick-client-save') return salvarClienteRapido();
  if (action === 'os-cliente-select') {
    const id = parseInt(el.getAttribute('data-id'));
    const nome = decodeURIComponent(el.getAttribute('data-nome') || '');
    const tel = decodeURIComponent(el.getAttribute('data-tel') || '');
    const doc = decodeURIComponent(el.getAttribute('data-doc') || '');
    if (id) return selecionarCliente(id, nome, tel, doc);
  }
  if (action === 'os-peca-adicionar') {
    const osId = parseInt(el.getAttribute('data-os-id'));
    if (osId) return adicionarPecaOS(osId);
  }
  if (action === 'os-peca-select') {
    const pecaId = parseInt(el.getAttribute('data-id'));
    const peca = (PECAS_DATA || []).find(item => String(item.id) === String(pecaId));
    if (peca) return selecionarPeca(peca);
  }
  if (action === 'os-peca-remover') {
    const osId = parseInt(el.getAttribute('data-os-id'));
    const pecaId = parseInt(el.getAttribute('data-peca-id'));
    if (osId && pecaId) return removerPecaOS(osId, pecaId);
  }
});

document.addEventListener('input', (e) => {
  if (e.target && e.target.matches('[data-action="os-total-recalc"]')) calcTotal();
});
document.addEventListener('DOMContentLoaded', preencherClienteSelecionadoInicial);
