const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

function abrirModalNovaPeca() {
  openModal('Nova Peça', `
    <form method="POST" action="/estoque/nova">
      <input type="hidden" name="_csrf_token" value="${CSRF}">
      <div class="form-row fr2">
        <div class="form-group"><label>Nome *</label><input type="text" name="nome" required autofocus></div>
        <div class="form-group"><label>Código SKU</label><input type="text" name="codigo"></div>
      </div>
      <div class="form-row fr2">
        <div class="form-group"><label>Categoria</label><input type="text" name="categoria" placeholder="Ex: memória, fonte, HD"></div>
        <div class="form-group"><label>Localização</label><input type="text" name="localizacao" placeholder="Ex: Prateleira A3"></div>
      </div>
      <div class="form-row fr3">
        <div class="form-group"><label>Quantidade</label><input type="number" name="quantidade" value="0" min="0"></div>
        <div class="form-group"><label>Estoque Mínimo</label><input type="number" name="estoque_minimo" value="5" min="0"></div>
        <div class="form-group"><label>Margem %</label><input type="number" name="margem" value="0" step="0.01" min="0"></div>
      </div>
      <div class="form-group"><label>Custo (R$)</label><input type="number" name="custo" value="0" step="0.01" min="0"></div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="submit" class="btn btn-primary">Salvar</button>
      </div>
    </form>`);
}

function abrirModalMovimentacao(id) {
  const p = PECAS_DATA.find(x => x.id === id);
  if (!p) return;
  openModal(`↕ Movimentar Estoque — ${p.nome}`, `
    <form method="POST" action="/estoque/${id}/movimentacao">
      <input type="hidden" name="_csrf_token" value="${CSRF}">
      <div class="alert a-blue mb16">Estoque atual: <strong>${p.quantidade}</strong> unidades (mínimo: ${p.estoque_minimo})</div>
      <div class="form-row fr2">
        <div class="form-group"><label>Tipo *</label>
          <select name="tipo" id="mov-tipo">
            <option value="entrada">📥 Entrada (compra)</option>
            <option value="saida">📤 Saída (uso/perda)</option>
            <option value="ajuste">🔧 Ajuste manual</option>
          </select>
        </div>
        <div class="form-group"><label>Quantidade *</label><input type="number" name="quantidade" min="0" value="1" required></div>
      </div>
      <div class="form-group"><label>Justificativa *</label><input type="text" name="justificativa" minlength="5" maxlength="300" required placeholder="Compra, perda, inventario..."></div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-action="close-modal">Cancelar</button>
        <button type="submit" class="btn btn-primary">Confirmar</button>
      </div>
    </form>`);
}

function abrirModalLote(id) {
  const p = PECAS_DATA.find(x => x.id === id);
  if (!p) return;
  openModal(`Receber lote - ${p.nome}`, `
    <div class="form-row fr2"><div class="form-group"><label>Codigo do lote *</label><input id="lot-code" maxlength="100" required></div><div class="form-group"><label>Localizacao</label><input id="lot-location" maxlength="100"></div></div>
    <div class="form-row fr3"><div class="form-group"><label>Quantidade *</label><input id="lot-quantity" type="number" min="1" value="1"></div><div class="form-group"><label>Custo unitario *</label><input id="lot-cost" type="number" min="0" step="0.01" value="${p.custo || 0}"></div><div class="form-group"><label>Validade</label><input id="lot-expiry" type="date"></div></div>
    <div class="form-group"><label>Justificativa *</label><input id="lot-reason" minlength="5" maxlength="300" value="Entrada de mercadoria"></div>
    <div class="modal-actions"><button class="btn btn-ghost" data-action="close-modal">Cancelar</button><button class="btn btn-primary" data-action="peca-lote-salvar" data-id="${id}">Receber lote</button></div>`);
}

async function salvarLote(id) {
  const payload = {
    codigo: document.getElementById('lot-code')?.value || '',
    localizacao: document.getElementById('lot-location')?.value || '',
    quantidade: parseInt(document.getElementById('lot-quantity')?.value || 0),
    custo_unitario: parseFloat(document.getElementById('lot-cost')?.value || 0),
    validade: document.getElementById('lot-expiry')?.value || '',
    justificativa: document.getElementById('lot-reason')?.value || '',
  };
  const result = await apiFetch('POST', `/api/pecas/${id}/lotes`, payload);
  if (result) location.reload();
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'peca-nova') return abrirModalNovaPeca();
  if (action === 'peca-movimentar') {
    const id = parseInt(el.getAttribute('data-id'));
    if (id) return abrirModalMovimentacao(id);
  }
  if (action === 'peca-lote') return abrirModalLote(parseInt(el.getAttribute('data-id')));
  if (action === 'peca-lote-salvar') return salvarLote(parseInt(el.getAttribute('data-id')));
});
