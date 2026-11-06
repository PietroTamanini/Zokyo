(() => {
  'use strict';

  const commonPasswords = new Set([
    '12345678', '123456789', '1234567890', 'password', 'senha123',
    'qwerty123', 'abc12345', 'iloveyou', 'admin123', 'welcome1',
    'monkey12', 'dragon12', 'master12', 'letmein1', 'superman',
    'batman12', 'charlie1', 'donald12', 'passw0rd', 'p@ssword',
    'senha1234', 'zokyo123', '123mudar', 'mudar123', 'teste123',
    'temp1234', 'change12', 'default1', 'system12', 'root1234',
  ]);

  function passwordRules(password) {
    return {
      length: password.length >= 8,
      uppercase: /[A-Z]/.test(password),
      lowercase: /[a-z]/.test(password),
      number: /\d/.test(password),
      special: /[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/.test(password),
      common: Boolean(password) && !commonPasswords.has(password.toLowerCase()),
    };
  }

  function update(policy, input) {
    const password = input.value;
    const rules = passwordRules(password);
    const entries = Object.entries(rules);
    const passed = entries.filter(([, valid]) => valid).length;
    policy.dataset.strength = password ? String(passed) : '0';
    policy.querySelectorAll('[data-password-rule]').forEach((item) => {
      const valid = rules[item.dataset.passwordRule];
      item.classList.toggle('is-valid', Boolean(valid));
      item.classList.toggle('is-invalid', Boolean(password) && !valid);
    });
    const score = policy.querySelector('[data-password-score]');
    if (score) score.textContent = password ? `${passed} de 6 requisitos atendidos` : 'Digite uma senha para conferir';
  }

  function init() {
    document.querySelectorAll('[data-password-policy]').forEach((policy) => {
      const input = policy.closest('.form-group')?.querySelector('[data-password-input]');
      if (!input) return;
      input.addEventListener('input', () => update(policy, input));
      update(policy, input);
    });
  }

  window.ZokyoPasswordPolicy = { passwordRules };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
