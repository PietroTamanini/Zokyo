/**
 * viacep.js — Integração com a API pública ViaCEP
 *
 * Uso: adicione a classe `mask-cep` e `data-viacep` no input de CEP.
 * Configure os campos de destino com atributos `data-fill-*`:
 *
 *   <input
 *     class="mask-cep"
 *     data-viacep
 *     data-fill-logradouro="#id-do-endereco"
 *     data-fill-bairro="#id-do-bairro"
 *     data-fill-cidade="#id-da-cidade"
 *     data-fill-uf="#id-do-uf"
 *   >
 *
 * Os seletores podem ser IDs (#meu-campo), nomes ([name=cidade])
 * ou qualquer seletor CSS válido — buscados dentro do modal/formulário
 * mais próximo para funcionar com conteúdo dinâmico.
 *
 * Caso os atributos não sejam definidos, o módulo tenta auto-detectar
 * campos pelo name: endereco, logradouro, bairro, cidade, uf.
 *
 * Funcionalidades:
 *   ✅ Busca automática ao completar 8 dígitos
 *   ✅ Indicador de carregamento no campo
 *   ✅ Feedback visual de sucesso/erro
 *   ✅ Não sobrescreve campos já preenchidos pelo usuário
 *   ✅ Funciona com formulários dinâmicos (modais)
 *   ✅ Debounce para evitar chamadas duplicadas
 *   ✅ Tratamento de CEP inexistente
 */

const ViaCEP = (() => {
  'use strict';

  const API_URL = 'https://viacep.com.br/ws/{cep}/json/';
  const DEBOUNCE_MS = 400;
  let _timer = null;
  let _lastCep = '';

  /* ── Utilitários ─────────────────────────────────────────── */

  const soDigitos = v => (v || '').replace(/\D/g, '');

  /** Resolve um seletor dentro do container mais próximo do campo */
  function resolveField(cepEl, selector) {
    if (!selector) return null;
    // Busca dentro do modal body ou form mais próximo, depois no document
    const container =
      cepEl.closest('#m-body') ||
      cepEl.closest('.modal-body') ||
      cepEl.closest('form') ||
      document;
    return container.querySelector(selector);
  }

  /** Auto-detecção de campos pelo name quando data-fill-* não está definido */
  function autoDetect(cepEl, fieldName) {
    const container =
      cepEl.closest('#m-body') ||
      cepEl.closest('.modal-body') ||
      cepEl.closest('form') ||
      document;

    // Tenta vários nomes comuns
    const candidates = {
      logradouro: ['[name=logradouro]', '[id*=logradouro]', '[name=endereco]', '[id*=endereco]', '#c-end'],
      bairro:     ['[name=bairro]', '[id*=bairro]', '#c-bairro'],
      cidade:     ['[name=cidade]', '[id*=cidade]', '#c-cidade'],
      uf:         ['[name=uf]', '[id*=uf]', '#c-uf', '[maxlength="2"]'],
    };

    const list = candidates[fieldName] || [];
    for (const sel of list) {
      const el = container.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  /* ── Visual feedback ─────────────────────────────────────── */

  function setLoading(el, loading) {
    const wrapper = el.parentElement;
    let icon = wrapper.querySelector('.cep-status');
    if (!icon) {
      icon = document.createElement('span');
      icon.className = 'cep-status';
      wrapper.classList.add('cep-wrapper');
      wrapper.appendChild(icon);
    }
    if (loading) {
      icon.textContent = '⏳';
      icon.title = 'Buscando CEP...';
      el.classList.add('cep-input-loading');
    } else {
      icon.textContent = '';
      el.classList.remove('cep-input-loading');
    }
    return icon;
  }

  function setSuccess(el, cidade) {
    const icon = setLoading(el, false);
    icon.textContent = '✅';
    icon.title = `Endereço encontrado: ${cidade}`;
    el.classList.add('cep-input-loading');
    // Remove ícone após 3 s
    setTimeout(() => {
      icon.textContent = '';
      el.classList.remove('cep-input-loading');
    }, 3000);
  }

  function setError(el, msg) {
    const icon = setLoading(el, false);
    icon.textContent = '❌';
    icon.title = msg;
    el.classList.add('cep-input-loading');
    // Mostra toast se disponível
    if (typeof showToast === 'function') showToast(msg, 'amber');
    setTimeout(() => {
      icon.textContent = '';
      el.classList.remove('cep-input-loading');
    }, 4000);
  }

  /* ── Preenchimento de campos ─────────────────────────────── */

  /**
   * Preenche um campo apenas se estiver vazio ou se forceOverwrite for true.
   * Dispara eventos input e change para acionar máscaras/validadores.
   */
  function fillField(el, value, forceOverwrite = false) {
    if (!el || !value) return;
    if (!forceOverwrite && el.value.trim() !== '') return; // não sobrescreve
    el.value = value;
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    // Animação sutil de preenchimento
    el.classList.add('field-autofilled');
    setTimeout(() => { el.classList.remove('field-autofilled'); }, 1200);
  }

  /* ── Busca na API ────────────────────────────────────────── */

  async function buscarCEP(cepEl, cep) {
    setLoading(cepEl, true);

    let data;
    try {
      const res = await fetch(
        API_URL.replace('{cep}', cep),
        {
          signal: AbortSignal.timeout(8000),
          headers: { 'Accept': 'application/json' },
        }
      );

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (err) {
      if (err.name === 'TimeoutError' || err.name === 'AbortError') {
        setError(cepEl, 'Tempo esgotado ao consultar CEP. Verifique sua conexão.');
      } else {
        setError(cepEl, 'Erro ao consultar CEP. Preencha o endereço manualmente.');
      }
      return;
    }

    if (data.erro) {
      setError(cepEl, `CEP ${cep.replace(/(\d{5})(\d{3})/, '$1-$2')} não encontrado.`);
      return;
    }

    // ── Resolve campos de destino ──────────────────────────
    const get = name =>
      resolveField(cepEl, cepEl.dataset['fill' + name.charAt(0).toUpperCase() + name.slice(1)]) ||
      autoDetect(cepEl, name);

    const logradouroEl = get('logradouro');
    const bairroEl     = get('bairro');
    const cidadeEl     = get('cidade');
    const ufEl         = get('uf');

    // Monta endereço completo se não há campo separado de bairro
    const enderecoCompleto = [data.logradouro, data.bairro]
      .filter(Boolean).join(', ');

    if (logradouroEl) {
      // Se há campo separado de bairro, coloca só logradouro; senão, endereço completo
      fillField(logradouroEl, bairroEl ?data.logradouro : enderecoCompleto);
    }
    if (bairroEl)  fillField(bairroEl, data.bairro);
    if (cidadeEl)  fillField(cidadeEl, data.localidade);
    if (ufEl) {
      fillField(ufEl, data.uf);
      // Para inputs com maxlength="2", garante uppercase
      if (ufEl.value) ufEl.value = ufEl.value.toUpperCase();
    }

    setSuccess(cepEl, data.localidade);

    // Foca no próximo campo não preenchido após o CEP
    const nextEmpty = [logradouroEl, bairroEl, cidadeEl].find(
      el => el && !el.value.trim()
    );
    if (nextEmpty) setTimeout(() => nextEmpty.focus(), 150);
  }

  /* ── Event delegation ────────────────────────────────────── */

  document.addEventListener('input', e => {
    const el = e.target;
    if (!el.classList || !el.classList.contains('mask-cep')) return;
    if (!el.hasAttribute('data-viacep')) return;

    const cep = soDigitos(el.value);
    if (cep.length !== 8) return;
    if (cep === _lastCep) return; // sem mudança real

    clearTimeout(_timer);
    _timer = setTimeout(() => {
      _lastCep = cep;
      buscarCEP(el, cep);
    }, DEBOUNCE_MS);
  });

  // Permite busca manual ao pressionar Enter no campo CEP
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const el = e.target;
    if (!el.classList || !el.classList.contains('mask-cep')) return;
    if (!el.hasAttribute('data-viacep')) return;
    const cep = soDigitos(el.value);
    if (cep.length === 8) {
      e.preventDefault();
      clearTimeout(_timer);
      _lastCep = '';  // força nova busca
      buscarCEP(el, cep);
    }
  });

  return { buscar: buscarCEP };
})();
