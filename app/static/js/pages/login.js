document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  const password = document.getElementById('senha');
  const toggle = document.getElementById('toggle-password');
  const caps = document.getElementById('caps-lock-status');
  const submit = document.getElementById('login-submit');

  toggle?.addEventListener('click', () => {
    const visible = password.type === 'text';
    password.type = visible ? 'password' : 'text';
    toggle.textContent = visible ? 'Mostrar' : 'Ocultar';
    toggle.setAttribute('aria-pressed', String(!visible));
    password.focus();
  });

  const updateCaps = event => {
    const active = Boolean(event.getModifierState?.('CapsLock'));
    caps.hidden = !active;
  };
  password?.addEventListener('keydown', updateCaps);
  password?.addEventListener('keyup', updateCaps);
  password?.addEventListener('blur', () => { caps.hidden = true; });

  form?.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    submit.disabled = true;
    submit.textContent = 'Entrando...';
  });
});
