# wpp-server.js — Bridge WhatsApp

Servidor Node.js opcional que conecta o Zokyo ao WhatsApp Web por meio do WPPConnect. Permite envio automático de mensagens da aplicação Flask para clientes.

Sem este servidor, o Zokyo continua funcionando normalmente e usa fallback com link `wa.me`.

## Visão Geral

```
Flask → HTTP local → wpp-server.js → WPPConnect → WhatsApp Web
```

O servidor:

- mantém uma sessão WhatsApp Web autenticada;
- disponibiliza endpoints HTTP locais;
- protege endpoints com token compartilhado;
- aplica rate limit;
- expõe status, QR Code, reconexão e envio de mensagem.

## Requisitos

- Node.js 18 ou superior;
- npm;
- uma conta WhatsApp disponível para pareamento;
- variável `WPP_SECRET` definida em produção.

## Dependências Node

Declaradas em `package.json`:

- `@wppconnect-team/wppconnect` ^2.2.0
- `express` ^5.x
- `express-rate-limit` ^8.x
- `helmet` ^8.x
- `dotenv` ^16.x

## Instalação

Na raiz do projeto:

```bash
npm install
```

## Configuração

Variáveis no `.env` da aplicação Flask (usadas também pelo servidor Node via `dotenv`):

```env
WPP_PORT=3333
WPP_SECRET=segredo_compartilhado_forte
WPP_SERVER_URL=http://127.0.0.1:3333
```

O mesmo `WPP_SECRET` deve ser usado no Flask e no Node.

## Execução

Desenvolvimento:

```bash
WPP_SECRET=segredo_compartilhado node wpp-server.js
```

Windows PowerShell:

```powershell
$env:WPP_SECRET="segredo_compartilhado"
node wpp-server.js
```

Na primeira execução, escaneie o QR Code com o WhatsApp:

```
WhatsApp → Dispositivos conectados → Conectar dispositivo
```

## Endpoints

Todos os endpoints protegidos exigem o header:

```http
X-Wpp-Token: <WPP_SECRET>
```

### `GET /`

Healthcheck simples do servidor.

### `GET /status`

Retorna o estado da sessão.

```json
{ "status": "conectado" }
```

### `GET /qr`

Retorna o QR Code atual quando a sessão ainda não está conectada.

### `POST /reconectar`

Reinicia o fluxo de conexão e solicita novo pareamento quando necessário.

### `POST /send`

Envia mensagem.

Request:

```json
{
  "number": "5547999999999",
  "message": "Olá! Sua OS está pronta para retirada."
}
```

Response:

```json
{ "ok": true }
```

## Segurança

O servidor aplica:

- `helmet` (headers HTTP);
- limite de payload JSON;
- rate limit global;
- rate limit específico para `/send`;
- autenticação por `X-Wpp-Token`;
- bloqueio de acesso remoto quando `WPP_SECRET` não está definido.

Recomendações:

- rode o servidor apenas em `127.0.0.1` ou rede confiável;
- não exponha a porta `3333` publicamente;
- use segredo forte e diferente da `SECRET_KEY` do Flask;
- monitore logs e reinícios;
- use PM2 ou systemd em produção.

## Produção com PM2

```bash
npm install -g pm2
WPP_SECRET=segredo_compartilhado pm2 start wpp-server.js --name zokyo-wpp
pm2 save
pm2 startup
```

Operação:

```bash
pm2 status
pm2 logs zokyo-wpp
pm2 restart zokyo-wpp
```

## Formato de Número

Use DDI + DDD + número, somente dígitos:

```
5547999999999
```

O Flask normaliza números comuns antes de chamar o servidor.

## Fallback do Flask

Quando `WPP_SERVER_URL` não está configurado, está offline ou retorna erro, o Flask retorna um link:

```
https://wa.me/<numero>?text=<mensagem>
```

O atendente pode então enviar a mensagem manualmente sem interromper o fluxo da OS.

## Troubleshooting

| Sintoma | Causa provável | Ação |
| --- | --- | --- |
| `401 Unauthorized` | token ausente ou diferente | conferir `WPP_SECRET` no Flask e Node |
| QR não aparece | sessão travada ou processo antigo | chamar `/reconectar` ou reiniciar o processo |
| mensagem não envia | WhatsApp desconectado | verificar `/status` e parear novamente |
| Flask cai no modo manual | servidor offline ou URL bloqueada | verificar `WPP_SERVER_URL`, porta e logs |
| rate limit | muitas mensagens em pouco tempo | aguardar janela de limite ou revisar automações |

## Observações Operacionais

- O WhatsApp Web pode encerrar sessões periodicamente; monitore via `/status`.
- Não use a mesma conta em múltiplos ambientes ao mesmo tempo.
- Evite disparos em massa: este bridge é para notificações operacionais de OS.
- A API oficial da Meta é a opção recomendada para alto volume ou uso crítico regulado.
