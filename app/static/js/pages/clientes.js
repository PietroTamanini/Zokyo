const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatarCpfCnpj(valor) {
  const d = soDigitos(valor || '').slice(0, 14);
  return d.length > 11 ? formatarCNPJ(d) : formatarCPF(d);
}

function clienteFormHtml(c = null) {
  const isEdit = Boolean(c?.id);
  const doc = c ? (c.cpf_cnpj_raw || c.cpf || c.cnpj || '') : '';
  return `
    <form id="cliente-form" data-validate>
      <div class="form-row fr2">
        <div class="form-group">
          <label>Nome *</label>
          <input type="text" name="nome" value="${escapeHtml(c?.nome)}" required
                 data-label="Nome" class="validate-required" data-min="2"
                 placeholder="Ex: Joao da Silva">
        </div>
        <div class="form-group">
          <label>CPF/CNPJ</label>
          <input type="text" name="cpf_cnpj" value="${escapeHtml(formatarCpfCnpj(doc))}"
                 class="mask-cpf-cnpj validate-cpf-cnpj" data-label="CPF/CNPJ"
                 placeholder="CPF ou CNPJ">
        </div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>Telefone</label>
          <input type="text" name="telefone" value="${escapeHtml(c?.telefone ? formatarTelefone(c.telefone) : '')}"
                 class="mask-phone validate-phone" data-label="Telefone"
                 placeholder="(00) 00000-0000">
        </div>
        <div class="form-group">
          <label>CEP</label>
          <input type="text" name="cep" value="${escapeHtml(c?.cep ? formatarCEP(c.cep) : '')}"
                 class="mask-cep validate-cep" data-label="CEP"
                 data-viacep
                 data-fill-logradouro="[name=endereco]"
                 data-fill-cidade="[name=cidade]"
                 data-fill-uf="[name=uf]"
                 placeholder="00000-000">
        </div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>Endereço</label>
          <input type="text" name="endereco" value="${escapeHtml(c?.endereco)}"
                 placeholder="Rua, avenida, travessa">
        </div>
        <div class="form-group">
          <label>Número da casa</label>
          <input type="text" name="numero_casa" value="${escapeHtml(c?.numero_casa)}"
                 placeholder="Ex: 217">
        </div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>Cidade</label>
          <input type="text" name="cidade" value="${escapeHtml(c?.cidade)}" placeholder="Ex: Joinville">
        </div>
        <div class="form-group">
          <label>UF</label>
          <input type="text" name="uf" value="${escapeHtml(c?.uf)}" maxlength="2" placeholder="SC">
        </div>
      </div>
      ${isEdit ? `
      <div class="form-group">
        <label>Status</label>
        <select name="ativo">
          <option value="1" ${c.ativo ? 'selected' : ''}>Ativo</option>
          <option value="0" ${!c.ativo ? 'selected' : ''}>Inativo</option>
        </select>
      </div>` : ''}
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="button" class="btn btn-primary" data-action="cliente-salvar" data-id="${c?.id || ''}">Salvar</button>
      </div>
    </form>`;
}

function abrirModalNovoCliente() {
  openModal('Novo Cliente', clienteFormHtml());
}

function abrirModalEditarCliente(id) {
  const c = CLIENTES_EDITAR.find(x => x.id === id);
  if (!c) return;
  openModal('Editar Cliente', clienteFormHtml(c));
}

function aplicarErrosCliente(errors = {}) {
  const form = document.getElementById('cliente-form');
  if (!form) return;
  Object.entries(errors).forEach(([field, message]) => showFieldError(form, field, message));
}

function restaurarClienteComErro() {
  if (typeof CLIENTE_FORM_STATE === 'undefined' || !CLIENTE_FORM_STATE.mode) return;
  const data = CLIENTE_FORM_STATE.data || {};
  if (CLIENTE_FORM_STATE.mode === 'edit') {
    openModal('Editar Cliente', clienteFormHtml(data));
  } else {
    openModal('Novo Cliente', clienteFormHtml(data));
  }
  const form = document.getElementById('cliente-form');
  form?.querySelectorAll('.mask-cpf-cnpj, .mask-phone, .mask-cep').forEach((el) => {
    if (typeof aplicarMascara === 'function') aplicarMascara(el);
  });
  aplicarErrosCliente(CLIENTE_FORM_STATE.errors || {});
}

function formPayload(form) {
  return {
    nome: form.elements.nome?.value || '',
    cpf_cnpj: form.elements.cpf_cnpj?.value || '',
    telefone: form.elements.telefone?.value || '',
    cep: form.elements.cep?.value || '',
    endereco: form.elements.endereco?.value || '',
    numero_casa: form.elements.numero_casa?.value || '',
    cidade: form.elements.cidade?.value || '',
    uf: form.elements.uf?.value || '',
    ativo: form.elements.ativo ? form.elements.ativo.value === '1' : true,
    _csrf_token: CSRF,
  };
}

function clearFieldErrors(form) {
  form.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
  form.querySelectorAll('.field-error').forEach(el => el.remove());
}

function showFieldError(form, field, message) {
  const name = field === 'documento' || field === 'cpf' || field === 'cnpj' ? 'cpf_cnpj' : field;
  const input = form.elements[name] || form.elements.nome;
  if (!input) {
    showToast(message || 'Erro no formulario.', 'red');
    return;
  }
  input.classList.add('input-error');
  let hint = input.parentElement.querySelector('.field-error');
  if (!hint) {
    hint = document.createElement('span');
    hint.className = 'field-error';
    input.parentElement.appendChild(hint);
  }
  hint.textContent = message;
  hint.classList.remove('hidden');
  input.focus();
}

async function salvarCliente(id = null) {
  const form = document.getElementById('cliente-form');
  if (!form) return;
  clearFieldErrors(form);
  if (window.DJValidators && !DJValidators.validate(form)) return;

  const payload = formPayload(form);
  const result = await apiCall(id ? 'PUT' : 'POST', id ? `/api/clientes/${id}` : '/api/clientes', payload);
  if (result.ok && result.data?.success !== false) {
    showToast(id ? 'Cliente atualizado.' : 'Cliente salvo.', 'green');
    window.location.reload();
    return;
  }
  const data = result.data || {};
  showFieldError(form, data.field || 'geral', data.message || data.erro || 'Não foi possível salvar o cliente.');
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'cliente-novo') return abrirModalNovoCliente();
  if (action === 'cliente-editar') {
    const id = parseInt(el.getAttribute('data-id'));
    if (id) return abrirModalEditarCliente(id);
  }
  if (action === 'cliente-salvar') {
    const id = parseInt(el.getAttribute('data-id'));
    return salvarCliente(id || null);
  }
});

document.addEventListener('DOMContentLoaded', restaurarClienteComErro);
