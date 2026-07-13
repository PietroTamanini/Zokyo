/**
 * validators.js — Validadores client-side com feedback em tempo real
 *
 * Uso básico:
 *   <input type="email" class="validate-email" data-label="E-mail">
 *
 * Classes disponíveis:
 *   .validate-required  — campo obrigatório
 *   .validate-email     — formato de e-mail
 *   .validate-cpf       — CPF com dígitos verificadores
 *   .validate-cnpj      — CNPJ com dígitos verificadores
 *   .validate-phone     — telefone BR
 *   .validate-cep       — CEP
 *   .validate-password  — política de senha forte
 *
 * Atributos opcionais:
 *   data-label="Nome"       — usa nas mensagens de erro
 *   data-min="3"            — mínimo de caracteres
 *   data-max="200"          — máximo de caracteres
 *   data-match="#outro-id"  — campo deve ser igual ao outro
 *
 * API:
 *   DJValidators.validate(form)    → true se válido
 *   DJValidators.validateField(el) → true se válido
 */

const DJValidators = (() => {
  'use strict';

  /* ── Utilitários ─────────────────────────────────────────────── */

  const soDigitos = v => (v || '').replace(/\D/g, '');

  function showError(el, msg) {
    el.classList.add('input-error');
    el.classList.remove('input-ok');
    let hint = el.parentElement.querySelector('.field-error');
    if (!hint) {
      hint = document.createElement('span');
      hint.className = 'field-error';
      el.parentElement.appendChild(hint);
    }
    hint.textContent = msg;
    hint.classList.remove('hidden');
  }

  function clearError(el) {
    el.classList.remove('input-error');
    el.classList.add('input-ok');
    const hint = el.parentElement.querySelector('.field-error');
    if (hint) hint.classList.add('hidden');
  }

  function getLabel(el) {
    return el.dataset.label ||
      el.closest('.form-group')?.querySelector('label')?.textContent?.replace('*', '').trim() ||
      el.name || 'Campo';
  }

  /* ── Algoritmo CPF ───────────────────────────────────────────── */
  function validarCPF(cpf) {
    const d = soDigitos(cpf);
    if (d.length !== 11) return false;
    if (new Set(d).size === 1) return false;
    let s1 = 0, s2 = 0;
    for (let i = 0; i < 9; i++) s1 += parseInt(d[i]) * (10 - i);
    const r1 = (s1 * 10 % 11) % 10;
    if (r1 !== parseInt(d[9])) return false;
    for (let i = 0; i < 10; i++) s2 += parseInt(d[i]) * (11 - i);
    const r2 = (s2 * 10 % 11) % 10;
    return r2 === parseInt(d[10]);
  }

  /* ── Algoritmo CNPJ ──────────────────────────────────────────── */
  function validarCNPJ(cnpj) {
    const d = soDigitos(cnpj);
    if (d.length !== 14) return false;
    if (new Set(d).size === 1) return false;
    const p1 = [5,4,3,2,9,8,7,6,5,4,3,2];
    const p2 = [6,5,4,3,2,9,8,7,6,5,4,3,2];
    const calc = (digits, weights) => {
      const s = digits.reduce((acc, n, i) => acc + parseInt(n) * weights[i], 0);
      const r = s % 11;
      return r < 2 ? 0 : 11 - r;
    };
    const arr = d.split('');
    const r1 = calc(arr.slice(0,12), p1);
    if (r1 !== parseInt(d[12])) return false;
    const r2 = calc(arr.slice(0,13), p2);
    return r2 === parseInt(d[13]);
  }

  /* ── Validação de telefone ───────────────────────────────────── */
  function validarTelefone(tel) {
    const d = soDigitos(tel);
    if (d.length < 10 || d.length > 11) return false;
    const ddd = parseInt(d.slice(0, 2));
    const dddsValidos = [
      11,12,13,14,15,16,17,18,19,
      21,22,24,27,28,
      31,32,33,34,35,37,38,
      41,42,43,44,45,46,47,48,49,
      51,53,54,55,
      61,62,63,64,65,66,67,68,69,
      71,73,74,75,77,79,
      81,82,83,84,85,86,87,88,89,
      91,92,93,94,95,96,97,98,99
    ];
    if (!dddsValidos.includes(ddd)) return false;
    const num = d.slice(2);
    if (num.length === 9 && num[0] !== '9') return false;
    if (num.length === 8 && !/^[2-8]/.test(num)) return false;
    return true;
  }

  /* ── Validação de e-mail ─────────────────────────────────────── */
  function validarEmail(email) {
    return /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(email.trim());
  }

  /* ── Validação de senha forte ────────────────────────────────── */
  function validarSenha(senha) {
    const erros = [];
    if (senha.length < 8)            erros.push('Mínimo 8 caracteres');
    if (!/[A-Z]/.test(senha))        erros.push('Ao menos 1 maiúscula');
    if (!/[a-z]/.test(senha))        erros.push('Ao menos 1 minúscula');
    if (!/\d/.test(senha))           erros.push('Ao menos 1 número');
    if (!/[!@#$%^&*()\-_=+\[\]{};:'",.<>?/\\|`~]/.test(senha))
      erros.push('Ao menos 1 caractere especial');
    return erros;
  }

  /* ── Indicador de força de senha ─────────────────────────────── */
  function updateStrengthIndicator(el, senha) {
    let indicator = el.parentElement.querySelector('.password-strength');
    if (!indicator) return;
    const erros = validarSenha(senha);
    const force = Math.max(0, 5 - erros.length);
    const labels = ['', 'Muito fraca', 'Fraca', 'Razoável', 'Boa', 'Forte'];
    indicator.textContent = senha ? labels[force] : '';
    indicator.className = `password-strength${senha ? ` strength-${force}` : ''}`;
  }

  /* ── Validar um campo individual ─────────────────────────────── */
  function validateField(el) {
    const value    = el.value;
    const trimmed  = value.trim();
    const label    = getLabel(el);
    const classes  = el.classList;
    const required = classes.contains('validate-required') || el.hasAttribute('required');

    // Obrigatório
    if (required && !trimmed) {
      showError(el, `${label} é obrigatório.`);
      return false;
    }

    // Se vazio e não obrigatório, ok
    if (!trimmed) {
      clearError(el);
      return true;
    }

    // Mínimo de caracteres
    const minLen = parseInt(el.dataset.min || '0');
    if (minLen && trimmed.length < minLen) {
      showError(el, `${label} deve ter pelo menos ${minLen} caracteres.`);
      return false;
    }

    // Máximo de caracteres
    const maxLen = parseInt(el.dataset.max || '0');
    if (maxLen && trimmed.length > maxLen) {
      showError(el, `${label} deve ter no máximo ${maxLen} caracteres.`);
      return false;
    }

    // E-mail
    if (classes.contains('validate-email')) {
      if (!validarEmail(trimmed)) {
        showError(el, 'E-mail inválido. Use o formato usuario@dominio.com.');
        return false;
      }
    }

    // CPF
    if (classes.contains('validate-cpf')) {
      if (!validarCPF(trimmed)) {
        showError(el, 'CPF inválido.');
        return false;
      }
    }

    // CNPJ
    if (classes.contains('validate-cnpj')) {
      if (!validarCNPJ(trimmed)) {
        showError(el, 'CNPJ inválido.');
        return false;
      }
    }

    // CPF/CNPJ
    if (classes.contains('validate-cpf-cnpj')) {
      const digits = soDigitos(trimmed);
      if (digits.length === 11) {
        if (!validarCPF(digits)) {
          showError(el, 'CPF invalido.');
          return false;
        }
      } else if (digits.length === 14) {
        if (!validarCNPJ(digits)) {
          showError(el, 'CNPJ invalido.');
          return false;
        }
      } else {
        showError(el, 'CPF/CNPJ deve ter 11 ou 14 digitos.');
        return false;
      }
    }

    // Telefone
    if (classes.contains('validate-phone')) {
      if (!validarTelefone(trimmed)) {
        showError(el, 'Telefone inválido. Use DDD + número (ex: 47 99999-9999).');
        return false;
      }
    }

    // CEP
    if (classes.contains('validate-cep')) {
      const cepDigits = soDigitos(trimmed);
      if (cepDigits.length !== 8 || cepDigits === '00000000') {
        showError(el, 'CEP inválido. Use o formato 00000-000.');
        return false;
      }
    }

    // Senha forte
    if (classes.contains('validate-password')) {
      const erros = validarSenha(value); // não trimmed — senhas preservam espaços
      if (erros.length > 0) {
        showError(el, erros[0]);
        updateStrengthIndicator(el, value);
        return false;
      }
      updateStrengthIndicator(el, value);
    }

    // Confirmação (match)
    if (el.dataset.match) {
      const target = document.querySelector(el.dataset.match);
      if (target && value !== target.value) {
        showError(el, 'Os campos não conferem.');
        return false;
      }
    }

    clearError(el);
    return true;
  }

  /* ── Validar formulário completo ─────────────────────────────── */
  function validate(form) {
    const fields = form.querySelectorAll(
      '.validate-required, .validate-email, .validate-cpf, ' +
      '.validate-cnpj, .validate-cpf-cnpj, .validate-phone, .validate-cep, .validate-password, ' +
      '[data-min], [data-max], [data-match]'
    );
    let valid = true;
    fields.forEach(el => {
      if (!validateField(el)) valid = false;
    });
    if (!valid) {
      // Foca o primeiro campo com erro
      const firstError = form.querySelector('.input-error');
      if (firstError) firstError.focus();
    }
    return valid;
  }

  /* ── Auto-validação em blur/input ────────────────────────────── */
  document.addEventListener('DOMContentLoaded', () => {
    const selector = [
      '.validate-required', '.validate-email', '.validate-cpf',
      '.validate-cnpj', '.validate-cpf-cnpj', '.validate-phone', '.validate-cep', '.validate-password',
      '[data-min]', '[data-max]', '[data-match]',
    ].join(', ');

    // Valida ao sair do campo (blur) — feedback imediato
    document.addEventListener('blur', e => {
      if (e.target.matches && e.target.matches(selector)) {
        validateField(e.target);
      }
    }, true);

    // Atualiza indicador de força de senha em tempo real
    document.addEventListener('input', e => {
      if (e.target.matches && e.target.classList.contains('validate-password')) {
        updateStrengthIndicator(e.target, e.target.value);
      }
    });

    // Impede submit de formulários com erros
    document.querySelectorAll('form[data-validate]').forEach(form => {
      form.addEventListener('submit', e => {
        if (!validate(form)) {
          e.preventDefault();
          e.stopPropagation();
        }
      });
    });
  });

  /* ── CSS dinâmico para os indicadores ───────────────────────── */
  return { validate, validateField };
})();

window.DJValidators = DJValidators;
