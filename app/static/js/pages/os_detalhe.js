/**
 * pages/os_detalhe.js
 * Lógica do detalhe da OS: envio de WhatsApp via Evolution API ou simulação.
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
      alert('Erro: ' + data.erro);
      return;
    }

    // ── Modo real: Evolution API enviou com sucesso ──
    if (data.modo === 'evolution' && data.sucesso) {
      showToast('✅ Mensagem enviada via WhatsApp!', 'green');
      return;
    }

    // ── Modo simulação ou falha na Evolution API ──
    // Abre wa.me com mensagem pré-preenchida
    if (data.link) {
      window.open(data.link, '_blank');
      if (data.modo === 'simulacao') {
        showToast('💬 WhatsApp aberto. Clique em Enviar no app.', 'blue');
      } else {
        showToast('⚠ Evolution API offline. Abrindo wa.me.', 'amber');
      }
    }

  } catch (err) {
    alert('Erro de conexão: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '💬 WhatsApp';
    }
  }
}

function showToast(msg, color = 'blue') {
  const toast = document.createElement('div');
  const allowed = ['green', 'blue', 'amber', 'red'];
  toast.className = `toast toast-${allowed.includes(color) ? color : 'blue'}`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}
