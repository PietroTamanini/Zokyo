(function () {
  const cfg = window.DJTECH_SITE || {};
  document.querySelectorAll('[data-whatsapp-link]').forEach((link) => {
    const text = encodeURIComponent('Olá, vim pelo site da DJ Tech e preciso de atendimento.');
    link.href = `https://wa.me/${cfg.whatsapp}?text=${text}`;
  });
  document.querySelectorAll('[data-current-year]').forEach((node) => {
    node.textContent = String(new Date().getFullYear());
  });

  const header = document.querySelector('.site-header');
  const syncHeader = () => header?.classList.toggle('is-scrolled', window.scrollY > 16);
  syncHeader();
  window.addEventListener('scroll', syncHeader, { passive: true });
})();
