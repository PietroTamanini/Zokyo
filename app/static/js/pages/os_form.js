// Busca de clientes
const dropdown = document.getElementById('cliente-dropdown');
const input    = document.getElementById('cliente-busca');
const hiddenId = document.getElementById('cliente_id');

function _soDigitos(v) { return (v||'').replace(/\D/g,''); }
function _formatCPF(v) {
  const d = _soDigitos(v).slice(0,11);
  return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/,'$1.$2.$3-$4');
}

if (input) {
  input.addEventListener('input', function () {
    const q        = this.value.trim().toLowerCase();
    const qDigitos = _soDigitos(q);           // para busca por CPF sem formatação
    if (q.length < 2) { dropdown.style.display='none'; return; }

    const matches = (CLIENTES_DATA||[]).filter(c => {
      const nomeOk = c.nome.toLowerCase().includes(q);
      // compara dígitos do CPF (suporta busca com ou sem máscara)
      const cpfOk  = qDigitos.length >= 2 && (c.cpf||'').includes(qDigitos);
      return nomeOk || cpfOk;
    });

    if (!matches.length) { dropdown.style.display='none'; return; }

    dropdown.innerHTML = matches.slice(0,8).map(c => {
      const nome = encodeURIComponent(c.nome || '');
      const tel  = encodeURIComponent(c.telefone || '');
      const cpf  = encodeURIComponent(c.cpf || '');
      const cpfFmt = c.cpf ? _formatCPF(c.cpf) : '';
      return `
      <div data-action="os-cliente-select" data-id="${c.id}"
           data-nome="${nome}" data-tel="${tel}" data-cpf="${cpf}"
           style="padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--border);font-size:13px">
        <strong>${c.nome}</strong>
        <span style="color:var(--text-3);font-size:11px;margin-left:8px">
          ${c.telefone||''} ${cpfFmt ? '· '+cpfFmt : ''}
        </span>
      </div>`;
    }).join('');
    dropdown.style.display = 'block';
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#cliente-busca') && !e.target.closest('#cliente-dropdown'))
      dropdown.style.display='none';
  });
}

function selecionarCliente(id, nome, tel, cpf) {
  hiddenId.value = id;
  input.value    = nome;
  dropdown.style.display = 'none';
  document.getElementById('cliente-card').style.display = 'block';
  document.getElementById('cliente-info').innerHTML =
    `<strong>${nome}</strong> · ${tel||'—'} · <span style="font-family:'JetBrains Mono',monospace;font-size:11px">${cpf ? _formatCPF(cpf) : ''}</span>`;
}
function trocarCliente() {
  hiddenId.value = '';
  input.value = '';
  document.getElementById('cliente-card').style.display = 'none';
  input.focus();
}

// Cálculo do total
function calcTotal() {
  const mo  = parseFloat(document.getElementById('f-mo')?.value||0);
  const vp  = parseFloat(document.getElementById('f-vp')?.value||0);
  const dc  = parseFloat(document.getElementById('f-dc')?.value||0);
  const tot = Math.max(0, mo + vp - dc);
  const el  = document.getElementById('total-display');
  if (el) el.textContent = 'R$ ' + tot.toFixed(2).replace('.',',').replace(/(\d)(?=(\d{3})+,)/g,'$1.');
}

// Adicionar peça à OS
async function adicionarPecaOS(osId) {
  const pid = document.getElementById('os-peca-id')?.value;
  const qtd = parseInt(document.getElementById('os-peca-qtd')?.value||1);
  const vlr = parseFloat(document.getElementById('os-peca-vlr')?.value||0);
  if (!pid) { showToast('Selecione uma peça', 'amber'); return; }
  const r = await apiCall('POST', `/api/os/${osId}/pecas`, {peca_id:parseInt(pid), quantidade:qtd, valor_unitario:vlr});
  if (r.ok) location.reload();
  else showToast(r.data.erro||'Erro ao adicionar peça','red');
}
async function removerPecaOS(osId, pecaId) {
  if (!confirm('Remover esta peça da OS?')) return;
  const r = await apiCall('DELETE', `/api/os/${osId}/pecas/${pecaId}`);
  if (r.ok) location.reload();
  else showToast(r.data.erro||'Erro ao remover','red');
}

// Auto-preenche valor da peça ao selecionar
document.getElementById('os-peca-id')?.addEventListener('change', function() {
  const opt   = this.options[this.selectedIndex];
  const preco = opt?.getAttribute('data-preco') || 0;
  const el    = document.getElementById('os-peca-vlr');
  if (el) el.value = parseFloat(preco).toFixed(2);
});

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'os-cliente-trocar') return trocarCliente();
  if (action === 'os-cliente-select') {
    const id   = parseInt(el.getAttribute('data-id'));
    const nome = decodeURIComponent(el.getAttribute('data-nome') || '');
    const tel  = decodeURIComponent(el.getAttribute('data-tel')  || '');
    const cpf  = decodeURIComponent(el.getAttribute('data-cpf')  || '');
    if (id) return selecionarCliente(id, nome, tel, cpf);
  }
  if (action === 'os-peca-adicionar') {
    const osId = parseInt(el.getAttribute('data-os-id'));
    if (osId) return adicionarPecaOS(osId);
  }
  if (action === 'os-peca-remover') {
    const osId   = parseInt(el.getAttribute('data-os-id'));
    const pecaId = parseInt(el.getAttribute('data-peca-id'));
    if (osId && pecaId) return removerPecaOS(osId, pecaId);
  }
});

document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('[data-action="os-cliente-select"]');
  if (el) el.style.background = 'var(--blue-glow)';
});
document.addEventListener('mouseout', (e) => {
  const el = e.target.closest('[data-action="os-cliente-select"]');
  if (el) el.style.background = '';
});
document.addEventListener('input', (e) => {
  if (e.target && e.target.matches('[data-action="os-total-recalc"]')) calcTotal();
});