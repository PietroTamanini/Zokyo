const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function abrirModalNovaTransacao() {
  const hoje = new Date().toISOString().split('T')[0];
  openModal('Nova Transação', `
    <form method="POST" action="/financeiro/nova">
      <input type="hidden" name="_csrf_token" value="${CSRF}">
      <div class="form-row fr2">
        <div class="form-group"><label>Tipo *</label>
          <select name="tipo">
            <option value="receita">💚 Receita</option>
            <option value="despesa">🔴 Despesa</option>
          </select>
        </div>
        <div class="form-group"><label>Categoria</label>
          <select name="categoria">
            <option value="servico">Serviço</option>
            <option value="peca">Peça</option>
            <option value="aluguel">Aluguel</option>
            <option value="salario">Salário</option>
            <option value="fornecedor">Fornecedor</option>
            <option value="imposto">Imposto</option>
            <option value="outros">Outros</option>
          </select>
        </div>
      </div>
      <div class="form-group"><label>Descrição *</label><input type="text" name="descricao" required autofocus placeholder="Ex: Reparo notebook Dell"></div>
      <div class="form-row fr2">
        <div class="form-group"><label>Valor (R$) *</label><input type="number" name="valor" step="0.01" min="0" required></div>
        <div class="form-group"><label>Vencimento</label><input type="date" name="data_vencimento" value="${hoje}"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Status</label>
          <select name="status">
            <option value="pendente">Pendente</option>
            <option value="pago">Pago</option>
          </select>
        </div>
        <div class="form-group"><label>Forma de Pagamento</label>
          <select name="forma_pagamento">
            <option value="">Selecione</option>
            <option>Dinheiro</option><option>PIX</option>
            <option>Cartão Débito</option><option>Cartão Crédito</option>
            <option>Transferência</option>
          </select>
        </div>
      </div>
      <div class="form-row fr3">
        <div class="form-group"><label>Parcelas</label><input type="number" name="parcelas" value="1" min="1" max="60"></div>
        <div class="form-group"><label>Recorrencia</label><select name="recorrencia"><option value="">Nao recorrente</option><option value="mensal">Mensal</option></select></div>
        <div class="form-group"><label>Comissao %</label><input type="number" name="comissao_percentual" value="0" min="0" max="100" step="0.01"></div>
      </div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="submit" class="btn btn-primary">Salvar</button>
      </div>
    </form>`);
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  if (el.getAttribute('data-action') === 'transacao-nova') {
    return abrirModalNovaTransacao();
  }
});
