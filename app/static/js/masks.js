/**
 * masks.js — Máscaras de input automáticas
 *
 * Classes CSS disponíveis:
 *   .mask-cpf      → 000.000.000-00
 *   .mask-cnpj     → 00.000.000/0000-00
 *   .mask-phone    → (00) 00000-0000 ou (00) 0000-0000
 *   .mask-cep      → 00000-000
 *   .mask-currency → R$ 0,00
 *   .mask-int      → apenas inteiros positivos
 *   .mask-decimal  → número decimal (ponto como separador)
 *
 * Funciona em campos estáticos E em modais criados dinamicamente
 * (event delegation — não depende de DOMContentLoaded).
 *
 * Helpers globais:
 *   soDigitos(v)      → remove tudo que não for dígito
 *   formatarCPF(v)    → formata string de dígitos como CPF
 *   formatarCNPJ(v)   → formata string de dígitos como CNPJ
 *   formatarCEP(v)    → formata string de dígitos como CEP
 *   formatarTelefone(v) → formata string de dígitos como telefone BR
 */

/* ── Helpers globais ──────────────────────────────────────────────── */

function soDigitos(v) {
  return (v || '').replace(/\D/g, '');
}

function formatarCPF(v) {
  const d = soDigitos(v).slice(0, 11);
  return d
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d{1,2})$/, '$1-$2');
}

function formatarCNPJ(v) {
  const d = soDigitos(v).slice(0, 14);
  return d
    .replace(/(\d{2})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1/$2')
    .replace(/(\d{4})(\d{1,2})$/, '$1-$2');
}

function formatarCEP(v) {
  const d = soDigitos(v).slice(0, 8);
  return d.replace(/(\d{5})(\d{1,3})$/, '$1-$2');
}

function formatarTelefone(v) {
  const d = soDigitos(v).slice(0, 11);
  if (d.length <= 10) {
    return d
      .replace(/(\d{2})(\d)/, '($1) $2')
      .replace(/(\d{4})(\d)/, '$1-$2');
  }
  return d
    .replace(/(\d{2})(\d)/, '($1) $2')
    .replace(/(\d{5})(\d)/, '$1-$2');
}

/* ── Aplicador com reposicionamento de cursor ─────────────────────── */

function aplicarMascara(el) {
  const cursorPos = el.selectionStart;
  const prevLen   = el.value.length;
  const v         = el.value;
  const c         = el.classList;

  if (c.contains('mask-cpf')) {
    el.value = formatarCPF(v);
  } else if (c.contains('mask-cnpj')) {
    el.value = formatarCNPJ(v);
  } else if (c.contains('mask-phone')) {
    el.value = formatarTelefone(v);
  } else if (c.contains('mask-cep')) {
    el.value = formatarCEP(v);
  } else if (c.contains('mask-int')) {
    el.value = soDigitos(v).slice(0, 9);
  } else if (c.contains('mask-decimal')) {
    let s = v.replace(/[^\d.]/g, '');
    const parts = s.split('.');
    if (parts.length > 2) s = parts[0] + '.' + parts.slice(1).join('');
    el.value = s;
  } else if (c.contains('mask-currency')) {
    const digits = soDigitos(v);
    if (!digits) { el.value = ''; return; }
    const cents   = parseInt(digits, 10);
    const intPart = Math.floor(cents / 100);
    const decPart = cents % 100;
    el.value = 'R$ ' + intPart.toLocaleString('pt-BR') + ',' + String(decPart).padStart(2, '0');
  }

  // Reposiciona cursor (mantém posição ao editar no meio do campo)
  const diff = el.value.length - prevLen;
  const newPos = Math.max(0, cursorPos + diff);
  try { el.setSelectionRange(newPos, newPos); } catch (_) {}
}

/* ── Event delegation ─────────────────────────────────────────────── */
// Captura no fase de captura (true) para pegar antes de outros listeners.
// Funciona em campos estáticos e em qualquer modal criado dinamicamente.

const _MASK_CLASSES = [
  'mask-cpf', 'mask-cnpj', 'mask-phone', 'mask-cep',
  'mask-int', 'mask-decimal', 'mask-currency',
];

document.addEventListener('input', function (e) {
  const el = e.target;
  if (!el || !el.classList) return;
  if (_MASK_CLASSES.some(m => el.classList.contains(m))) {
    aplicarMascara(el);
  }
}, true);

// Aplica máscara ao focar campo já preenchido (ex: editar cliente)
document.addEventListener('focus', function (e) {
  const el = e.target;
  if (!el || !el.classList || !el.value) return;
  const formatos = ['mask-cpf', 'mask-cnpj', 'mask-phone', 'mask-cep'];
  if (formatos.some(m => el.classList.contains(m))) {
    aplicarMascara(el);
  }
}, true);

/* ── Helper de valor numérico para campos moeda ───────────────────── */
// Compatível com o padrão anterior: el._getRawValue()
// Uso: const valor = document.getElementById('meu-campo')._getRawValue();

document.addEventListener('DOMContentLoaded', function () {
  function bindRawValue(el) {
    el._getRawValue = function () {
      const digits = soDigitos(el.value);
      return digits ? parseInt(digits, 10) / 100 : 0;
    };
  }
  document.querySelectorAll('.mask-currency').forEach(bindRawValue);

  // MutationObserver para campos de moeda criados dinamicamente
  const observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      m.addedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return;
        if (node.classList && node.classList.contains('mask-currency')) {
          bindRawValue(node);
        }
        node.querySelectorAll && node.querySelectorAll('.mask-currency').forEach(bindRawValue);
      });
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
});