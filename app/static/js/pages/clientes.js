const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function abrirModalNovoCliente() {
  openModal('Novo Cliente', `
    <div class="form-row fr2">
      <div class="form-group"><label>Nome *</label><input type="text" id="c-nome" required data-label="Nome" class="validate-required" data-min="2" placeholder="Ex: João da Silva"></div>
      <div class="form-group"><label>CPF</label><input type="text" id="c-cpf" class="mask-cpf validate-cpf" data-label="CPF" placeholder="000.000.000-00"></div>
    </div>
    <div class="form-row fr2">
      <div class="form-group"><label>Telefone</label><input type="text" id="c-tel" class="mask-phone validate-phone" data-label="Telefone" placeholder="(00) 00000-0000"></div>
      <div class="form-group"><label>E-mail</label><input type="email" id="c-email" class="validate-email" data-label="E-mail" placeholder="exemplo@email.com"></div>
    </div>
    <div class="form-row fr2">
      <div class="form-group">
        <label>CEP</label>
        <input type="text" id="c-cep" class="mask-cep validate-cep" data-label="CEP"
          data-viacep
          data-fill-logradouro="#c-endereco"
          data-fill-cidade="#c-cidade"
          data-fill-uf="#c-uf"
          placeholder="00000-000">
      </div>
      <div class="form-group"><label>Endereço</label><input type="text" id="c-endereco" placeholder="Rua, nº, complemento"></div>
    </div>
    <div class="form-row fr2">
      <div class="form-group"><label>Cidade</label><input type="text" id="c-cidade" placeholder="Ex: Joinville"></div>
      <div class="form-group"><label>UF</label><input type="text" id="c-uf" maxlength="2" placeholder="SC"></div>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
      <button class="btn btn-ghost" data-action="close-modal">Cancelar</button>
      <button class="btn btn-primary" data-action="cliente-salvar">Salvar</button>
    </div>`);
}

function salvarNovoCliente() {
  const nome = document.getElementById('c-nome').value.trim();
  if (!nome) { showToast('Nome é obrigatório', 'amber'); return; }

  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/clientes/novo';

  const fields = {
    _csrf_token: CSRF,
    nome,
    cpf:      document.getElementById('c-cpf')?.value      || '',
    telefone: document.getElementById('c-tel')?.value      || '',
    email:    document.getElementById('c-email')?.value    || '',
    cep:      document.getElementById('c-cep')?.value      || '',
    endereco: document.getElementById('c-endereco')?.value || '',
    cidade:   document.getElementById('c-cidade')?.value   || '',
    uf:       document.getElementById('c-uf')?.value       || '',
  };

  for (const [k, v] of Object.entries(fields)) {
    const i = document.createElement('input');
    i.type = 'hidden'; i.name = k; i.value = v;
    form.appendChild(i);
  }

  document.body.appendChild(form);
  form.submit();
}

function abrirModalEditarCliente(id) {
  const c = CLIENTES_EDITAR.find(x => x.id === id);
  if (!c) return;
  openModal('Editar Cliente', `
    <form method="POST" action="/clientes/${id}/editar">
      <input type="hidden" name="_csrf_token" value="${CSRF}">
      <div class="form-row fr2">
        <div class="form-group"><label>Nome *</label><input type="text" name="nome" value="${c.nome || ''}" required data-label="Nome" class="validate-required" data-min="2" placeholder="Ex: João da Silva"></div>
        <div class="form-group"><label>CPF</label><input type="text" name="cpf" value="${c.cpf ? formatarCPF(c.cpf) : ''}" class="mask-cpf validate-cpf" data-label="CPF" placeholder="000.000.000-00"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Telefone</label><input type="text" name="telefone" value="${c.telefone ? formatarTelefone(c.telefone) : ''}" class="mask-phone validate-phone" data-label="Telefone" placeholder="(00) 00000-0000"></div>
        <div class="form-group"><label>E-mail</label><input type="email" name="email" value="${c.email || ''}" class="validate-email" data-label="E-mail" placeholder="exemplo@email.com"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>CEP</label>
          <input type="text" name="cep" value="${c.cep ? formatarCEP(c.cep) : ''}" class="mask-cep validate-cep" data-label="CEP"
            data-viacep
            data-fill-logradouro="[name=endereco]"
            data-fill-cidade="[name=cidade]"
            data-fill-uf="[name=uf]"
            placeholder="00000-000">
        </div>
        <div class="form-group"><label>Endereço</label><input type="text" name="endereco" value="${c.endereco || ''}" placeholder="Rua, nº, complemento"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Cidade</label><input type="text" name="cidade" value="${c.cidade || ''}" placeholder="Ex: Joinville"></div>
        <div class="form-group"><label>UF</label><input type="text" name="uf" value="${c.uf || ''}" maxlength="2" placeholder="SC"></div>
      </div>
      <div class="form-group"><label>Status</label>
        <select name="ativo">
          <option value="1" ${c.ativo ? 'selected' : ''}>Ativo</option>
          <option value="0" ${!c.ativo ? 'selected' : ''}>Inativo</option>
        </select>
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="submit" class="btn btn-primary">Salvar</button>
      </div>
    </form>`);
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'cliente-novo')    return abrirModalNovoCliente();
  if (action === 'cliente-salvar')  return salvarNovoCliente();
  if (action === 'cliente-editar') {
    const id = parseInt(el.getAttribute('data-id'));
    if (id) return abrirModalEditarCliente(id);
  }
});