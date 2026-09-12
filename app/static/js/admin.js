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
