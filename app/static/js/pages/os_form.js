const dropdown = document.getElementById('cliente-dropdown');
const input = document.getElementById('cliente-busca');
const hiddenId = document.getElementById('cliente_id');
const partDropdown = document.getElementById('peca-dropdown');
const partInput = document.getElementById('os-peca-busca');
const partHiddenId = document.getElementById('os-peca-id');
const orderForm = document.querySelector('[data-os-form]');
const openingDurationInput = document.getElementById('opening-duration-seconds');
const fastbarTime = document.getElementById('fastbar-time');
const equipmentTypeSelect = document.querySelector('select[name="tipo_aparelho"]');
const equipmentOtherInput = document.querySelector('input[name="tipo_aparelho_outro"]');
const defectTextarea = document.querySelector('textarea[name="defeito_alegado"]');
const defectSuggestions = document.getElementById('defect-suggestions');
const entryChecklistPreview = document.getElementById('entry-checklist-preview');
const clienteCache = new Map();
const pecaCache = new Map();
const pecaById = new Map((PECAS_DATA || []).map(item => [String(item.id), item]));
let clienteTimer = null;
let pecaTimer = null;
let openingStartedAt = null;
let fastbarInterval = null;

const DEFECT_SUGGESTIONS = {
  Notebook: ['Nao liga', 'Tela quebrada', 'Nao carrega', 'Lento', 'Esquenta muito', 'Teclado falhando'],
  Smartphone: ['Tela quebrada', 'Nao carrega', 'Sem imagem', 'Bateria descarrega rapido', 'Molhou', 'Sem audio'],
  Desktop: ['Nao liga', 'Reinicia sozinho', 'Sem video', 'Lento', 'Faz barulho', 'Travando'],
  Tablet: ['Tela quebrada', 'Nao carrega', 'Nao liga', 'Touch falhando', 'Bateria ruim'],
  TV: ['Sem imagem', 'Sem som', 'Nao liga', 'Imagem piscando', 'Controle nao funciona'],
  Monitor: ['Sem imagem', 'Tela piscando', 'Manchas na tela', 'Fonte com falha', 'Cabo/conector danificado'],
  Impressora: ['Nao imprime', 'Atolando papel', 'Falha na conexao', 'Impressao manchada', 'Nao puxa papel'],
  Videogame: ['Nao liga', 'Sem imagem', 'Superaquecendo', 'Controle nao conecta', 'Leitor falhando'],
  Outros: ['Nao liga', 'Nao funciona corretamente', 'Falha intermitente', 'Barulho anormal', 'Conector danificado']
};

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
  items.forEach(item => pecaById.set(String(item.id), item));
  pecaCache.set(q, items);
  return items;
}

function tipoEquipamentoAtual() {
  const selected = equipmentTypeSelect?.value || '';
  if (selected === 'Outros') return equipmentOtherInput?.value.trim() || 'Outros';
  return selected || 'Outros';
}

function sugestoesParaTipo(tipo) {
  return DEFECT_SUGGESTIONS[tipo] || DEFECT_SUGGESTIONS.Outros;
}

function checklistParaTipo(tipo) {
  const normalized = String(tipo || '').trim().toLowerCase();
  return (CHECKLISTS_DATA || []).find(item => String(item.categoria || '').trim().toLowerCase() === normalized);
}

function renderDefectSuggestions() {
  if (!defectSuggestions) return;
  const tipo = tipoEquipamentoAtual();
  defectSuggestions.innerHTML = sugestoesParaTipo(tipo).map(text => `
    <button type="button" class="btn btn-ghost btn-xs defect-suggestion"
            data-action="defect-suggestion-add" data-text="${_safe(text)}">
      ${_safe(text)}
    </button>
  `).join('');
}

function renderEntryChecklistPreview() {
  if (!entryChecklistPreview) return;
  const tipo = tipoEquipamentoAtual();
  const checklist = checklistParaTipo(tipo);
  if (!checklist || !Array.isArray(checklist.itens) || !checklist.itens.length) {
    entryChecklistPreview.innerHTML = `
      <div class="entry-checklist-empty">
        Nenhum checklist ativo para ${_safe(tipo)}.
        <a href="/checklists">Cadastrar modelo</a>
      </div>
    `;
    return;
  }
  entryChecklistPreview.innerHTML = `
    <div class="entry-checklist-head">
      <strong>Checklist de entrada</strong>
      <span>${_safe(checklist.categoria)} v${_safe(checklist.versao)}</span>
    </div>
    <div class="entry-checklist-items">
      ${checklist.itens.map(item => `<span>${_safe(item)}</span>`).join('')}
    </div>
  `;
}

function adicionarSugestaoDefeito(text) {
  if (!defectTextarea || !text) return;
  const current = defectTextarea.value.trim();
  if (current.toLowerCase().includes(text.toLowerCase())) {
    defectTextarea.focus();
    return;
  }
  defectTextarea.value = current ?`${current}; ${text}` : text;
  defectTextarea.dispatchEvent(new Event('input', { bubbles: true }));
  defectTextarea.focus();
}

function startOpeningTimer() {
  if (openingStartedAt !== null) return;
  openingStartedAt = Date.now();
  updateFastbarTime();
  fastbarInterval = setInterval(updateFastbarTime, 1000);
}

function finishOpeningTimer() {
  if (!openingDurationInput) return;
  startOpeningTimer();
  const seconds = Math.max(0, Math.min(86400, Math.round((Date.now() - openingStartedAt) / 1000)));
  openingDurationInput.value = String(seconds);
}

function updateFastbarTime() {
  if (!fastbarTime) return;
  const seconds = openingStartedAt === null ?0 : Math.max(0, Math.round((Date.now() - openingStartedAt) / 1000));
  fastbarTime.textContent = seconds < 60 ?`${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function stepDone(step) {
  if (step === 'cliente') return Boolean(hiddenId?.value);
  if (step === 'equipamento') {
    const marca = orderForm?.querySelector('[name="marca"]')?.value.trim();
    const modelo = orderForm?.querySelector('[name="modelo"]')?.value.trim();
    return Boolean(tipoEquipamentoAtual() && marca && modelo);
  }
  if (step === 'defeito') return Boolean(defectTextarea?.value.trim());
  if (step === 'valor') return parseFloat(document.getElementById('f-mo')?.value || 0) > 0;
  return false;
}

function updateFastbarProgress() {
  document.querySelectorAll('[data-fast-step]').forEach(button => {
    const step = button.getAttribute('data-fast-step');
    button.classList.toggle('is-done', stepDone(step));
  });
}

function setCurrentFastbarStep(target) {
  if (!target?.name && !target?.id) return;
  const map = [
    ['cliente', ['cliente_id', 'cliente-busca']],
    ['equipamento', ['tipo_aparelho', 'tipo_aparelho_outro', 'marca', 'modelo', 'numero_serie']],
    ['defeito', ['defeito_alegado', 'defeito_encontrado', 'solucao', 'entrada_acessorios', 'entrada_estado_visual', 'entrada_senha_padrao', 'observacoes']],
    ['valor', ['valor_servico', 'desconto', 'garantia_dias', 'status', 'prio', 'tecnico_nome', 'tipo_atendimento', 'data_entrada', 'data_prev']]
  ];
  const current = map.find(([, names]) => names.includes(target.name) || names.includes(target.id))?.[0];
  document.querySelectorAll('[data-fast-step]').forEach(button => {
    button.classList.toggle('is-current', button.getAttribute('data-fast-step') === current);
  });
}

if (orderForm) {
  ['focusin', 'input', 'change', 'click'].forEach(eventName => {
    orderForm.addEventListener(eventName, startOpeningTimer, { once: true });
  });
  orderForm.addEventListener('submit', finishOpeningTimer);
  orderForm.addEventListener('input', updateFastbarProgress);
  orderForm.addEventListener('change', updateFastbarProgress);
  orderForm.addEventListener('focusin', e => setCurrentFastbarStep(e.target));
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
  updateFastbarProgress();
}

function trocarCliente() {
  hiddenId.value = '';
  input.value = '';
  document.getElementById('cliente-card').classList.add('is-hidden');
  input.focus();
  updateFastbarProgress();
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
  if (action === 'defect-suggestion-add') return adicionarSugestaoDefeito(el.getAttribute('data-text') || '');
  if (action === 'os-fast-submit') return orderForm?.requestSubmit();
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
    const peca = pecaById.get(String(pecaId));
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
  if (e.target && e.target.matches('input[name="tipo_aparelho_outro"]')) {
    renderDefectSuggestions();
    renderEntryChecklistPreview();
  }
});
document.addEventListener('DOMContentLoaded', preencherClienteSelecionadoInicial);
document.addEventListener('DOMContentLoaded', renderDefectSuggestions);
document.addEventListener('DOMContentLoaded', renderEntryChecklistPreview);
document.addEventListener('DOMContentLoaded', () => {
  updateFastbarTime();
  updateFastbarProgress();
});
equipmentTypeSelect?.addEventListener('change', () => {
  renderDefectSuggestions();
  renderEntryChecklistPreview();
  updateFastbarProgress();
});

document.querySelectorAll('[data-fast-step]').forEach(button => {
  button.addEventListener('click', () => {
    const target = document.querySelector(button.getAttribute('data-target'));
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    target?.querySelector('input, select, textarea, button')?.focus({ preventScroll: true });
  });
});
