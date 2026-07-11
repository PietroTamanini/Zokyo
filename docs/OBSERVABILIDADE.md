# Observabilidade

## Healthchecks

- `GET /healthz`: indica que o processo Flask esta respondendo.
- `GET /readyz`: executa `SELECT 1` no banco e retorna 503 se a conexao falhar.

Essas rotas nao exigem login e sao ignoradas pelo redirecionamento de primeiro acesso.

## Logs

O projeto ja possui auditoria em `EventoLog`. O modulo de laudos tambem registra eventos especificos em `laudo_eventos`.

Pendencias:

- logs estruturados com request ID;
- metrica de latencia e contadores por rota;
- Sentry opcional via `SENTRY_DSN`;
- dashboard de disponibilidade;
- alertas de falha de PDF, upload e WhatsApp.
