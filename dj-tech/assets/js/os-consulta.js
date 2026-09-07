(function () {
  const form = document.querySelector('#os-form');
  const result = document.querySelector('#os-result');
  const cfg = window.DJTECH_SITE || {};
  const apiBase = String(cfg.apiBase || '').replace(/\/$/, '');

  function onlyDigits(value) {
    return String(value || '').replace(/\D/g, '');
  }

  function formatDocument(value) {
    const digits = onlyDigits(value).slice(0, 14);

    if (digits.length <= 11) {
      return digits
        .replace(/^(\d{3})(\d)/, '$1.$2')
        .replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
        .replace(/^(\d{3})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3-$4');
    }

    return digits
      .replace(/^(\d{2})(\d)/, '$1.$2')
      .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
      .replace(/^(\d{2})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3/$4')
      .replace(/^(\d{2})\.(\d{3})\.(\d{3})\/(\d{4})(\d)/, '$1.$2.$3/$4-$5');
  }

  function formatDate(value) {
    if (!value) return 'Ainda não definido';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Ainda não definido';
    return date.toLocaleDateString('pt-BR');
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    }[char]));
  }

  function setState(type, html) {
    result.className = `result-panel is-${type}`;
    result.innerHTML = html;
    result.hidden = false;
  }

  const documentoInput = form?.elements.documento;
  documentoInput?.addEventListener('input', () => {
    documentoInput.value = formatDocument(documentoInput.value);
  });
  documentoInput?.addEventListener('paste', () => {
    window.setTimeout(() => {
      documentoInput.value = formatDocument(documentoInput.value);
    }, 0);
  });

  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const originalButtonHtml = button.innerHTML;
    const numero = onlyDigits(form.elements.numero.value);
    const documento = onlyDigits(form.elements.documento.value);

    if (!numero || ![11, 14].includes(documento.length)) {
      setState('warn', '<strong>Confira os dados.</strong><span>Informe o número da OS e o CPF/CNPJ usado no atendimento.</span>');
      return;
    }

    button.disabled = true;
    button.classList.add('is-loading');
    button.innerHTML = '<i class="bi bi-search me-2"></i>Consultando...';
    setState('loading', '<strong>Buscando OS...</strong><span>Estamos consultando a base da assistência.</span>');

    try {
      const response = await fetch(`${apiBase}/api/public/os-consulta`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ numero, documento }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.status) {
        setState('warn', `<strong>Não encontramos essa OS.</strong><span>${payload.message || 'Confira o número e o documento informado.'}</span>`);
        return;
      }

      const os = payload.result || {};
      setState('success', `
        <div class="result-head">
          <div><span>Ordem de serviço</span><strong>OS #${escapeHtml(os.numero)}</strong></div>
          <b>${escapeHtml(os.status_label || os.status || 'Em atendimento')}</b>
        </div>
        <div class="result-grid">
          <div><span>Cliente</span><strong>${escapeHtml(os.cliente || 'Cliente')}</strong></div>
          <div><span>Equipamento</span><strong>${escapeHtml(os.equipamento || 'Equipamento')}</strong></div>
          <div><span>Entrada</span><strong>${formatDate(os.entrada)}</strong></div>
          <div><span>Previsão</span><strong>${formatDate(os.previsao)}</strong></div>
          <div><span>Saída</span><strong>${formatDate(os.saida)}</strong></div>
          <div><span>Garantia</span><strong>${escapeHtml(os.garantia_dias || 90)} dias</strong></div>
        </div>
        <p>Para mais detalhes, fale com a equipe pelo WhatsApp.</p>
      `);
    } catch (_error) {
      setState('error', '<strong>Não foi possível consultar agora.</strong><span>Verifique se a consulta está ativa ou tente novamente em instantes.</span>');
    } finally {
      button.disabled = false;
      button.classList.remove('is-loading');
      button.innerHTML = originalButtonHtml;
    }
  });
})();
