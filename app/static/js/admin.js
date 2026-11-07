(() => {
  const form = document.querySelector('[data-company-form]');
  if (!form) return;
  const name = form.querySelector('[data-company-name]');
  const slug = form.querySelector('[data-company-slug]');
  const preview = form.querySelector('[data-domain-preview]');
  const updatePreview = () => {
    const value = (slug.value.trim() || name.value).normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '').toLowerCase()
      .replace(/[^a-z0-9-]+/g, '-').replace(/-{2,}/g, '-')
      .slice(0, 63).replace(/^-|-$/g, '') || 'nome-da-empresa';
    preview.textContent = `${value}.${form.dataset.baseDomain}`;
  };
  name.addEventListener('input', updatePreview);
  slug.addEventListener('input', updatePreview);
  updatePreview();
})();


(() => {
  const money = (value) => Number(value || 0).toLocaleString('pt-BR', {
    style: 'currency', currency: 'BRL', minimumFractionDigits: 2,
  });

  document.querySelectorAll('[data-hosting-plan-form]').forEach((container) => {
    const form = container.closest('form');
    const select = form?.querySelector('[data-plan-select]') || document.querySelector('[data-plan-select]');
    const checkbox = container.querySelector('[data-hosting-checkbox]');
    const summary = container.querySelector('[data-hosting-summary]');
    if (!select || !checkbox || !summary) return;

    const update = () => {
      const option = select.options[select.selectedIndex];
      const price = Number(option?.dataset.planPrice || 0);
      const percentage = Number(option?.dataset.hostingPercent || 0);
      const hasPlan = Boolean(select.value);
      checkbox.disabled = !hasPlan;
      if (!hasPlan) {
        checkbox.checked = false;
        summary.textContent = 'Selecione um plano para consultar o acréscimo de hospedagem.';
        return;
      }
      if (!percentage) {
        summary.textContent = 'Este plano não possui acréscimo configurado para hospedagem.';
        return;
      }
      const total = price * (1 + percentage / 100);
      summary.textContent = checkbox.checked
        ? `Hospedagem selecionada: +${percentage.toLocaleString('pt-BR')}% · total estimado ${money(total)}/mês.`
        : `Disponível por +${percentage.toLocaleString('pt-BR')}% · total com hospedagem ${money(total)}/mês.`;
    };
    select.addEventListener('change', update);
    checkbox.addEventListener('change', update);
    update();
  });
})();
