/**
 * wpp-server.js — Servidor Express local para integração WhatsApp via WPPConnect.
 *
 * V-07 FIX: rate limiting via express-rate-limit + remoção de X-Powered-By.
 *
 * Instalar dependências:
 *   npm install @wppconnect-team/wppconnect express express-rate-limit helmet
 *
 * Uso:
 *   WPP_SECRET=seu-segredo-forte node wpp-server.js
 *
 * Variáveis de ambiente:
 *   WPP_SECRET   — segredo compartilhado com o Flask (obrigatório em produção)
 *   WPP_PORT     — porta a escutar (padrão: 3333)
 *   WPP_SESSION  — nome da sessão WPPConnect (padrão: zokyo)
 */

"use strict";

require("dotenv").config();

const express     = require("express");
const rateLimit   = require("express-rate-limit");
const helmet      = require("helmet");
const wppconnect  = require("@wppconnect-team/wppconnect");

const PORT       = parseInt(process.env.WPP_PORT || "3333", 10);
const WPP_SECRET = (process.env.WPP_SECRET || "").trim();
const SESSION    = process.env.WPP_SESSION || "zokyo";

if (!WPP_SECRET) {
  console.warn(
    "[AVISO] WPP_SECRET não configurado. " +
    "Defina WPP_SECRET no ambiente para proteger o servidor."
  );
}

const app = express();

// ── V-07 FIX: remove X-Powered-By e aplica headers de segurança ───────────
app.disable("x-powered-by");
app.use(helmet({
  contentSecurityPolicy: false, // API JSON — CSP não se aplica
}));

// ── V-07 FIX: rate limiting global (proteção de DoS) ──────────────────────
const globalLimiter = rateLimit({
  windowMs : 60 * 1000,   // 1 minuto
  max      : 60,           // máx 60 req/min por IP globalmente
  message  : { erro: "Muitas requisições. Tente novamente mais tarde." },
  standardHeaders: true,
  legacyHeaders  : false,
});
app.use(globalLimiter);

// ── V-07 FIX: rate limiting específico para /send (anti-spam) ─────────────
const sendLimiter = rateLimit({
  windowMs : 60 * 1000,   // 1 minuto
  max      : 30,           // máx 30 mensagens/min por IP
  message  : { erro: "Limite de envio atingido. Máximo 30 mensagens/minuto." },
  standardHeaders: true,
  legacyHeaders  : false,
});

app.use(express.json({ limit: "64kb" }));  // limita payload para evitar DoS

// ── Middleware de autenticação por token ────────────────────────────────────
function autenticar(req, res, next) {
  if (!WPP_SECRET) {
    // Sem segredo configurado: permite apenas de localhost
    const ip = req.socket.remoteAddress || "";
    if (ip !== "127.0.0.1" && ip !== "::1" && ip !== "::ffff:127.0.0.1") {
      return res.status(401).json({ erro: "WPP_SECRET não configurado e acesso remoto bloqueado." });
    }
    return next();
  }
  const token = req.headers["x-wpp-token"] || "";
  if (token !== WPP_SECRET) {
    return res.status(401).json({ erro: "Token inválido." });
  }
  next();
}

// ── Estado do cliente WPPConnect ────────────────────────────────────────────
let client = null;
let lastQr = null;
let lastQrAt = null;

async function inicializarCliente() {
  console.log(`[WPP] Inicializando sessão: ${SESSION}...`);
  try {
    client = await wppconnect.create({
      session          : SESSION,
      catchQR          : (qrCode, asciiQR) => {
        lastQr = _normalizeQr(qrCode);
        lastQrAt = new Date().toISOString();
        console.log("[WPP] Escaneie o QR Code abaixo:");
        console.log(asciiQR);
      },
      statusFind       : (statusSession) => {
        console.log(`[WPP] Status da sessão: ${statusSession}`);
      },
      logQR            : true,
      autoClose        : 0,
      browserArgs      : ["--no-sandbox", "--disable-setuid-sandbox"],
      disableWelcome   : true,
      updatesLog       : false,
    });
    console.log("[WPP] ✅ Cliente WPPConnect inicializado com sucesso.");
  } catch (err) {
    console.error("[WPP] ❌ Erro ao inicializar cliente:", err.message);
    client = null;
  }
}

function _normalizeQr(qrCode) {
  if (!qrCode) return null;
  if (typeof qrCode !== "string") return null;
  if (qrCode.startsWith("data:image")) return qrCode;
  return `data:image/png;base64,${qrCode}`;
}

async function _statusAtual() {
  if (!client) return { status: "desconectado" };
  try {
    const connected = await client.isConnected();
    if (connected) return { status: "conectado" };
    if (lastQr) return { status: "qr_pronto" };
    return { status: "desconectado" };
  } catch {
    return { status: "erro" };
  }
}

// ── Rotas ────────────────────────────────────────────────────────────────────

app.get("/", async (req, res) => {
  const st = await _statusAtual();
  res.json({ ok: true, ...st, qr: lastQr ? "disponivel" : "indisponivel" });
});

app.get("/status", autenticar, async (req, res) => {
  const st = await _statusAtual();
  res.json(st);
});

app.get("/qr", autenticar, async (req, res) => {
  if (!lastQr) {
    return res.status(404).json({ erro: "QR não disponível." });
  }
  res.json({ qr: lastQr, gerado_em: lastQrAt });
});

app.post("/reconectar", autenticar, async (req, res) => {
  try {
    if (client) {
      try { await client.close(); } catch {}
    }
    client = null;
    lastQr = null;
    lastQrAt = null;
    await inicializarCliente();
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ erro: "Falha ao reconectar.", detalhes: err.message });
  }
});

// V-07 FIX: rate limiting específico no /send
app.post("/send", autenticar, sendLimiter, async (req, res) => {
  const { number, message } = req.body || {};

  if (!number || !message) {
    return res.status(400).json({ erro: "number e message são obrigatórios." });
  }
  if (typeof number !== "string" || typeof message !== "string") {
    return res.status(400).json({ erro: "Tipos inválidos." });
  }
  if (message.length > 4096) {
    return res.status(400).json({ erro: "Mensagem excede 4096 caracteres." });
  }

  if (!client) {
    return res.status(503).json({ erro: "Cliente WhatsApp não inicializado." });
  }

  try {
    // Sanitiza número: apenas dígitos
    const sanitized = number.replace(/\D/g, "");
    let targetId = `${sanitized}@c.us`;

    // Compatibilidade entre versões do WPPConnect
    if (typeof client.getNumberId === "function") {
      const numberId = await client.getNumberId(sanitized);
      if (!numberId || !numberId._serialized) {
        return res.status(404).json({ erro: "Número não encontrado no WhatsApp." });
      }
      targetId = numberId._serialized;
    } else if (typeof client.checkNumberStatus === "function") {
      const status = await client.checkNumberStatus(sanitized);
      const serialized = status?.id?._serialized || status?.id || status?._serialized;
      if (status?.numberExists === false || !serialized) {
        return res.status(404).json({ erro: "Número não encontrado no WhatsApp." });
      }
      targetId = serialized;
    }

    await client.sendText(targetId, message);
    res.json({ ok: true });
  } catch (err) {
    console.error("[WPP] Erro ao enviar mensagem:", err.message);
    res.status(500).json({ erro: "Falha ao enviar mensagem.", detalhes: err.message });
  }
});

// ── Inicialização ─────────────────────────────────────────────────────────────
app.listen(PORT, "127.0.0.1", async () => {
  console.log(`[WPP] Servidor ouvindo em 127.0.0.1:${PORT}`);
  await inicializarCliente();
});

// Graceful shutdown
process.on("SIGTERM", async () => {
  console.log("[WPP] Encerrando...");
  if (client) {
    try { await client.close(); } catch {}
  }
  process.exit(0);
});
