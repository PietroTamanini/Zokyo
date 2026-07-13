# Observabilidade

## Healthchecks

- `GET /healthz`: indica que o processo Flask esta respondendo.
- `GET /readyz`: executa `SELECT 1` no banco e retorna 503 se a conexao falhar.

Essas rotas nao exigem login e sao ignoradas pelo redirecionamento de primeiro acesso.

## Logs

Em producao, os logs sao JSON e mascaram tokens, documentos e e-mails. Cada resposta inclui `X-Request-ID`; um valor valido recebido nesse header e propagado, caso contrario o servidor gera um identificador aleatorio. O projeto tambem possui auditoria em `EventoLog` e eventos especificos em `laudo_eventos`.

## Metricas

`GET /metrics` exporta contadores e histogramas Prometheus por metodo, rota normalizada e status. O acesso exige sessao administrativa ou:

```http
Authorization: Bearer <METRICS_TOKEN>
```

Configure um token longo e aleatorio em producao. Nao exponha essa rota publicamente sem autenticacao.

## Sentry

Defina `SENTRY_DSN` para habilitar captura de erros. `send_default_pii` permanece desativado. A amostragem de traces e controlada por `SENTRY_TRACES_SAMPLE_RATE`, cujo padrao e zero.

Dashboards e regras de alerta devem ser configurados no provedor de monitoramento escolhido. Monitore pelo menos disponibilidade, latencia, HTTP 5xx, espaco em disco, conexoes do banco, notificacoes em `failed` e ultima execucao bem-sucedida de backup.
