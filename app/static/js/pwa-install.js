(function () {
  const PROMPT_ID = 'pwa-install';
  const DISMISS_KEY = 'zokyo:pwa:v3:dismissed-until';
  const INSTALLED_KEY = 'zokyo:pwa:v3:installed';
  const DISMISS_MS = 6 * 60 * 60 * 1000;
  const FALLBACK_DELAY_MS = 1800;

  let deferredPrompt = null;
  let isVisible = false;
  let currentMode = 'manual';

  const ua = window.navigator.userAgent || '';
  const isIos = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroid = /android/i.test(ua);
  const isMobile = isIos || isAndroid || /mobile|mobi/i.test(ua);
  const isLocalhost = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
  const isSecureEnough = window.isSecureContext || isLocalhost;

  function byId(id) {
    return document.getElementById(id);
  }

  function isStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  }

  function dismissedNow() {
    const until = Number(localStorage.getItem(DISMISS_KEY) || 0);
    return Number.isFinite(until) && Date.now() < until;
  }

  function shouldSkip() {
    return isStandalone() || localStorage.getItem(INSTALLED_KEY) === '1' || dismissedNow();
  }

  function registerServiceWorker() {
    if (!isSecureEnough || !('serviceWorker' in navigator)) return;
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/service-worker.js', { scope: '/' }).catch(function () {});
    });
  }

  function manualHelp() {
    if (!isSecureEnough) {
      return '<strong>Instalacao bloqueada neste endereco</strong>Para instalar como app de verdade no celular, abra o Zokyo por HTTPS. Endereco em IP local com HTTP pode criar atalho, mas o navegador bloqueia a PWA nativa.';
    }
    if (isIos) {
      return '<strong>Instalacao no iPhone/iPad</strong>Abra no Safari, toque em Compartilhar e escolha "Adicionar a Tela de Inicio".';
    }
    if (isAndroid) {
      return '<strong>Instalacao no Android</strong>Se o botao nativo nao aparecer, abra no Chrome, toque no menu e escolha "Instalar app".';
    }
    return '<strong>Instalacao no PC</strong>No Chrome ou Edge, use o icone de instalacao na barra de endereco ou o menu do navegador.';
  }

  function setManualMode() {
    currentMode = 'manual';
    const primary = byId('pwa-install-primary');
    const help = byId('pwa-install-help');
    const text = byId('pwa-install-text');

    if (primary) primary.textContent = 'Entendi';
    if (text) {
      text.textContent = isMobile
        ? 'Instale no celular para abrir direto pela tela inicial.'
        : 'Instale no PC para abrir em uma janela propria, sem depender da aba do navegador.';
    }
    if (help) {
      help.innerHTML = manualHelp();
      help.hidden = false;
    }
  }

  function setNativeMode() {
    currentMode = 'native';
    const primary = byId('pwa-install-primary');
    const help = byId('pwa-install-help');
    const text = byId('pwa-install-text');

    if (primary) primary.textContent = 'Instalar agora';
    if (text) {
      text.textContent = isMobile
        ? 'Instale no celular para abrir direto pela tela inicial.'
        : 'Instale no PC para abrir em uma janela propria, sem depender da aba do navegador.';
    }
    if (help) {
      help.hidden = true;
      help.textContent = '';
    }
  }

  function showPrompt(mode) {
    const prompt = byId(PROMPT_ID);
    if (!prompt || shouldSkip()) return;

    if (mode === 'native') setNativeMode();
    else setManualMode();

    prompt.hidden = false;
    isVisible = true;
  }

  function hidePrompt(dismiss) {
    const prompt = byId(PROMPT_ID);
    if (prompt) prompt.hidden = true;
    isVisible = false;
    if (dismiss) {
      localStorage.setItem(DISMISS_KEY, String(Date.now() + DISMISS_MS));
    }
  }

  async function installNative() {
    if (!deferredPrompt) {
      const help = byId('pwa-install-help');
      if (help) {
        help.innerHTML = manualHelp();
        help.hidden = false;
      }
      return;
    }

    const promptEvent = deferredPrompt;
    deferredPrompt = null;
    promptEvent.prompt();

    const choice = await promptEvent.userChoice.catch(function () {
      return { outcome: 'dismissed' };
    });

    if (choice && choice.outcome === 'accepted') {
      localStorage.setItem(INSTALLED_KEY, '1');
      hidePrompt(false);
    } else {
      setManualMode();
    }
  }

  registerServiceWorker();

  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferredPrompt = event;
    localStorage.removeItem(DISMISS_KEY);
    showPrompt('native');
  });

  window.addEventListener('appinstalled', function () {
    localStorage.setItem(INSTALLED_KEY, '1');
    hidePrompt(false);
  });

  document.addEventListener('DOMContentLoaded', function () {
    const close = byId('pwa-install-close');
    const later = byId('pwa-install-later');
    const primary = byId('pwa-install-primary');

    if (close) close.addEventListener('click', function () { hidePrompt(true); });
    if (later) later.addEventListener('click', function () { hidePrompt(true); });
    if (primary) {
      primary.addEventListener('click', function () {
        if (currentMode === 'manual') {
          hidePrompt(true);
          return;
        }
        installNative();
      });
    }

    if (deferredPrompt) {
      showPrompt('native');
      return;
    }

    window.setTimeout(function () {
      if (deferredPrompt) {
        showPrompt('native');
        return;
      }
      showPrompt('manual');
    }, FALLBACK_DELAY_MS);
  });
})();
