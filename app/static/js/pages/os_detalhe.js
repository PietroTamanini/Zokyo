/**
 * pages/os_detalhe.js
 * Lógica do detalhe da OS: envio de WhatsApp pela Meta Cloud API ou link manual.
 */

async function enviarWhatsApp() {
  if (!OS_DATA || !OS_DATA.id) return;

  const btn = document.getElementById('btn-whatsapp');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Enviando...';
  }

  try {
    const resp = await fetch(`/api/os/${OS_DATA.id}/whatsapp`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
      }
    });

    const data = await resp.json();

    if (resp.status === 401) {
      showToast('Sessão expirada. Faça login novamente.', 'amber');
      if (location.pathname !== '/login') location.href = '/login';
      return;
    }
    if (resp.status === 403) {
      showToast('Acesso negado.', 'red');
      return;
    }

    if (data.erro) {
      showToast('Erro: ' + data.erro, 'red');
      return;
    }

    if (data.modo === 'whatsapp_cloud' && data.sucesso) {
      showToast('Mensagem enviada via WhatsApp.', 'green');
      return;
    }

    if (data.link) {
      window.open(data.link, '_blank');
      if (data.modo === 'simulacao') {
        showToast('WhatsApp aberto. Clique em Enviar no app.', 'blue');
      } else {
        showToast('Envio automatico indisponivel. Abrindo wa.me.', 'amber');
      }
    }

  } catch (err) {
    showToast('Erro de conexão: ' + err.message, 'red');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'WhatsApp';
    }
  }
}
