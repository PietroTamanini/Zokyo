# wpp-server.js - Bridge WhatsApp

Servidor Node.js opcional que conecta o Zokyo ao WhatsApp Web por meio do WPPConnect. Ele permite envio automatico de mensagens da aplicacao Flask para clientes.

Sem este servidor, o Zokyo continua funcionando normalmente e usa fallback com link `wa.me`.

## Visao Geral

```text
Flask -> HTTP local -> wpp-server.js -> WPPConnect -> WhatsApp Web
```

O servidor:

- mantem uma sessao WhatsApp Web autenticada;
- disponibiliza endpoints HTTP locais;
- protege endpoints com token compartilhado;
- aplica rate limit;
- expoe status, QR Code, reconexao e envio de mensagem.

## Requisitos

- Node.js 18 ou superior;
- npm;
- uma conta WhatsApp disponivel para pareamento;
- variavel `WPP_SECRET` definida em producao.

## Instalacao

Na raiz do projeto:

```bash
npm install
```

Dependencias principais:

- `@wppconnect-team/wppconnect`
- `express`
- `express-rate-limit`
- `helmet`
- `dotenv`

## Configuracao

Variaveis:

```env
WPP_PORT=3333
WPP_SECRET=segredo_compartilhado_forte
```

No `.env` da aplicacao Flask:

```env
WPP_SERVER_URL=http://127.0.0.1:3333
WPP_SECRET=segredo_compartilhado_forte
```

O mesmo `WPP_SECRET` deve ser usado no Flask e no Node.

## Execucao

Desenvolvimento:

```bash
WPP_SECRET=segredo_compartilhado node wpp-server.js
```

Windows PowerShell:

```powershell
$env:WPP_SECRET="segredo_compartilhado"
node wpp-server.js
```

Na primeira execucao, escaneie o QR Code com o WhatsApp:

```text
WhatsApp -> Dispositivos conectados -> Conectar dispositivo
```

## Endpoints

Todos os endpoints protegidos exigem:

```http
X-Wpp-Token: <WPP_SECRET>
```

### `GET /`

Healthcheck simples do servidor.

### `GET /status`

Retorna o estado da sessao.

```json
{
  "status": "conectado"
}
```

### `GET /qr`

Retorna o QR Code atual quando a sessao ainda nao esta conectada.

### `POST /reconectar`

Reinicia o fluxo de conexao e solicita novo pareamento quando necessario.

### `POST /send`

Envia mensagem.

Request:

```json
{
  "number": "5547999999999",
  "message": "Ola! Sua OS esta pronta para retirada."
}
```

Response:

```json
{
  "ok": true
}
```

## Seguranca

O servidor aplica:

- `helmet`;
- limite de payload JSON;
- rate limit global;
- rate limit especifico para `/send`;
- autenticacao por `X-Wpp-Token`;
- bloqueio de acesso remoto sem `WPP_SECRET`.

Recomendacoes:

- rode o servidor apenas em `127.0.0.1` ou rede confiavel;
- nao exponha a porta `3333` publicamente;
- use segredo forte e diferente da `SECRET_KEY` do Flask;
- monitore logs e reinicios;
- use PM2 ou systemd em producao.

## Producao com PM2

```bash
npm install -g pm2
WPP_SECRET=segredo_compartilhado pm2 start wpp-server.js --name zokyo-wpp
pm2 save
pm2 startup
```

Operacao:

```bash
pm2 status
pm2 logs zokyo-wpp
pm2 restart zokyo-wpp
```

## Formato de Numero

Use DDI + DDD + numero:

```text
5547999999999
```

O Flask normaliza numeros comuns antes de chamar o servidor.

## Fallback do Flask

Quando `WPP_SERVER_URL` nao esta configurado, esta offline ou falha, o Flask retorna um link:

```text
https://wa.me/<numero>?text=<mensagem>
```

Assim o atendimento pode enviar a mensagem manualmente sem interromper o fluxo da OS.

## Troubleshooting

| Sintoma | Causa provavel | Acao |
| --- | --- | --- |
| `401 Unauthorized` | token ausente ou diferente | conferir `WPP_SECRET` no Flask e Node |
| QR nao aparece | sessao travada ou servidor antigo | chamar `/reconectar` ou reiniciar o processo |
| mensagem nao envia | WhatsApp desconectado | abrir status e parear novamente |
| Flask cai no modo manual | servidor offline ou URL bloqueada | verificar `WPP_SERVER_URL`, porta e logs |
| rate limit | muitas mensagens em pouco tempo | aguardar janela de limite ou revisar automacoes |

## Observacoes Operacionais

- O WhatsApp Web pode encerrar sessoes periodicamente.
- Nao use a mesma conta em muitos ambientes ao mesmo tempo.
- Evite disparos em massa: este bridge e para notificacoes operacionais de OS.
- A API oficial da Meta e a opcao recomendada para alto volume ou uso critico regulado.
