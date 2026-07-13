const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function abrirModalNovoFornecedor() {
  openModal('Novo Fornecedor', `
    <form method="POST" action="/fornecedores/novo">
      <input type="hidden" name="_csrf_token" value="${CSRF}">
      <div class="form-row fr2">
        <div class="form-group"><label>Nome *</label><input type="text" name="nome" required autofocus class="validate-required" data-label="Nome" data-min="2" placeholder="Ex: Distribuidora ABC"></div>
        <div class="form-group"><label>CNPJ</label><input type="text" name="cnpj" class="mask-cnpj validate-cnpj" data-label="CNPJ" placeholder="00.000.000/0001-00"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Telefone</label><input type="text" name="telefone" class="mask-phone validate-phone" data-label="Telefone" placeholder="(00) 00000-0000"></div>
        <div class="form-group"><label>E-mail</label><input type="email" name="email" class="validate-email" data-label="E-mail" placeholder="contato@empresa.com.br"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>CEP</label>
          <input type="text" name="cep" class="mask-cep validate-cep" data-label="CEP"
            data-viacep
            data-fill-logradouro="[name=endereco]"
            data-fill-cidade="[name=cidade]"
            placeholder="00000-000">
        </div>
        <div class="form-group"><label>Endereço</label><input type="text" name="endereco" placeholder="Rua, nº, complemento"></div>
      </div>
      <div class="form-group"><label>Cidade</label><input type="text" name="cidade" placeholder="Ex: Joinville"></div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="submit" class="btn btn-primary">Salvar</button>
      </div>
    </form>`);
}

function abrirModalEditarFornecedor(id) {
  const f = FORNECEDORES_DATA.find(x => x.id === id);
  if (!f) return;
  openModal('Editar Fornecedor', `
    <form method="POST" action="/fornecedores/${id}/editar">
      <input type="hidden" name="_csrf_token" value="${CSRF}">
      <div class="form-row fr2">
        <div class="form-group"><label>Nome *</label><input type="text" name="nome" value="${f.nome || ''}" required class="validate-required" data-label="Nome" data-min="2" placeholder="Ex: Distribuidora ABC"></div>
        <div class="form-group"><label>CNPJ</label><input type="text" name="cnpj" value="${f.cnpj ? formatarCNPJ(f.cnpj) : ''}" class="mask-cnpj validate-cnpj" data-label="CNPJ" placeholder="00.000.000/0001-00"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Telefone</label><input type="text" name="telefone" value="${f.telefone ? formatarTelefone(f.telefone) : ''}" class="mask-phone validate-phone" data-label="Telefone" placeholder="(00) 00000-0000"></div>
        <div class="form-group"><label>E-mail</label><input type="email" name="email" value="${f.email || ''}" class="validate-email" data-label="E-mail" placeholder="contato@empresa.com.br"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group">
          <label>CEP</label>
          <input type="text" name="cep" value="${f.cep ? formatarCEP(f.cep) : ''}" class="mask-cep validate-cep" data-label="CEP"
            data-viacep
            data-fill-logradouro="[name=endereco]"
            data-fill-cidade="[name=cidade]"
            placeholder="00000-000">
        </div>
        <div class="form-group"><label>Endereço</label><input type="text" name="endereco" value="${f.endereco || ''}" placeholder="Rua, nº, complemento"></div>
      </div>
      <div class="form-group"><label>Cidade</label><input type="text" name="cidade" value="${f.cidade || ''}" placeholder="Ex: Joinville"></div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="submit" class="btn btn-primary">Salvar</button>
      </div>
    </form>`);
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'fornecedor-novo') return abrirModalNovoFornecedor();
  if (action === 'fornecedor-editar') {
    const id = parseInt(el.getAttribute('data-id'));
    if (id) return abrirModalEditarFornecedor(id);
  }
});
