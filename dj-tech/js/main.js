(function () {
  const navbar = document.querySelector('#mainNavbar');
  const navLinks = document.querySelectorAll('a[href^="#"]');

  function updateNavbar() {
    if (!navbar) return;
    navbar.classList.toggle('is-scrolled', window.scrollY > 12);
  }

  navLinks.forEach((link) => {
    link.addEventListener('click', (event) => {
      const targetId = link.getAttribute('href');
      const target = targetId ? document.querySelector(targetId) : null;
      if (!target) return;

      event.preventDefault();
      const top = target.getBoundingClientRect().top + window.scrollY - 82;
      window.scrollTo({ top, behavior: 'smooth' });

      const openedMenu = document.querySelector('.navbar-collapse.show');
      const toggler = document.querySelector('.navbar-toggler');
      if (openedMenu && toggler) toggler.click();
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const openedMenu = document.querySelector('.navbar-collapse.show');
    const toggler = document.querySelector('.navbar-toggler');
    if (openedMenu && toggler) toggler.click();
  });

  updateNavbar();
  window.addEventListener('scroll', updateNavbar, { passive: true });
})();
