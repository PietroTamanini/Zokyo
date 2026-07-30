# Configuracao

Copie `.env.example` para `.env` em desenvolvimento e ajuste os valores locais.

## Obrigatorias

- `SECRET_KEY`: chave forte para sessoes e criptografia derivada.
- `DATABASE_URL`: URL SQLAlchemy do MySQL/MariaDB.
- `ENCRYPTION_SALT`: salt Base64 aleatorio de 32 bytes para segredos persistidos em `Configuracao`.

Em producao, `SECRET_KEY`, `DATABASE_URL` e `ENCRYPTION_SALT` sao validadas no startup.

## Recomendadas

- `REPORTS_UPLOAD_FOLDER`: pasta privada dos laudos. Se vazia, usa `instance/uploads/reports`.
- `REPORTS_PUBLIC_VERIFICATION`: habilita/desabilita a rota publica de verificacao de laudos.
- `PROXY_COUNT`: numero de proxies confiaveis na frente do Flask.
- `SCHEDULER_ENABLED`: mantenha `false` na aplicacao; use `true` somente no processo dedicado.
- `PASSWORD_RESET_TTL_MINUTES`: validade do link de recuperacao, padrao 30 minutos.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`: servidor de e-mail.
- `MAIL_FROM`: remetente usado na recuperacao de senha.
- `METRICS_TOKEN`: token Bearer para coleta protegida de metricas Prometheus.
- `SENTRY_DSN`: habilita Sentry opcional; vazio mantem a integracao desligada.
- `SENTRY_TRACES_SAMPLE_RATE`: amostragem entre 0 e 1, padrao 0.
- `ASAAS_API_KEY`: chave da API Asaas para gerar cobranças reais.
- `ASAAS_SANDBOX`: use `true` em homologação e `false` em produção.
- `ASAAS_BASE_URL`: sobrescreve a URL da API Asaas somente quando necessário.
- `ASAAS_TIMEOUT`: timeout HTTP das chamadas ao Asaas, em segundos.
- `ASAAS_USER_AGENT`: identificação enviada ao Asaas nas chamadas HTTP.

Sem `SMTP_HOST` e `MAIL_FROM`, nenhuma mensagem de recuperacao e enviada em producao e o erro operacional e registrado sem expor o token.

Sem `ASAAS_API_KEY`, as cobranças continuam usando o fallback local seguro. Com a chave configurada, o gateway `asaas` cria/consulta cliente, gera cobrança e busca o payload PIX quando a forma for Pix.

## 2FA administrativo

Administradores ativam TOTP em **Configuracoes > Seguranca da conta**. A ativacao exige um codigo valido do autenticador. Os codigos de recuperacao sao exibidos uma vez e persistidos somente como SHA-256. Para desativar, o sistema exige a senha atual e um TOTP valido.

O segredo TOTP e criptografado com uma chave derivada de `SECRET_KEY` e `ENCRYPTION_SALT`. Alterar esses valores sem planejamento torna os segredos existentes ilegíveis; mantenha-os no backup seguro de configuracao.

## Geradores

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

## Laudos

Arquivos sensiveis de laudos nao devem ficar em `static/`. Use armazenamento privado no filesystem ou, futuramente, uma implementacao compativel com S3.

# Inicializacao idempotente

Depois das migracoes, execute `flask --app wsgi:app seed-system`. O comando pode ser repetido e mantem os planos sandbox globais atualizados sem duplicacao.
