# Deploy

Estado revisado em 2026-11-02: build, Compose, migrations, staging, produção e rollback estão automatizados. Nenhum host real foi homologado nesta revisão; execute o [checklist de go-live](GO_LIVE.md) antes da liberação.

## Variaveis

Use `.env.production.example` como base. Em producao sao obrigatorias:

- `FLASK_ENV=production`
- `SECRET_KEY`
- `DATABASE_URL`
- `ENCRYPTION_SALT`
- `BLIND_INDEX_KEY`
- `PUBLIC_BASE_URL` ou `HEALTHCHECK_URL`
- `METRICS_TOKEN`
- `BACKUP_ENCRYPTION_KEY`
- `REPORTS_UPLOAD_FOLDER`
- `ALERT_EMAIL` ou `ALERT_WEBHOOK_URL`
- `SMTP_HOST` e `MAIL_FROM`
- `WHATSAPP_CLOUD_API_TOKEN`, `WHATSAPP_CLOUD_PHONE_NUMBER_ID` e `WHATSAPP_CLOUD_API_VERSION`
- `REDIS_URL`

## Migracoes

```bash
python -m flask --app wsgi:app db upgrade
```

Instalacoes novas executam a baseline consolidada `20260718_0001` automaticamente. Para um banco legado criado antes desta baseline, faca backup, confira o schema e marque a revision consolidada somente se o schema ja estiver equivalente:

```bash
python -m flask --app wsgi:app db stamp 20260718_0001
```

Nunca use `stamp` em banco vazio.

## Prontidao de producao

Antes de publicar ou promover uma versao, rode:

```bash
python -m flask --app wsgi:app production-check --strict-integrations
```

O comando reprova segredos fracos, banco nao produtivo, salt invalido, 2FA admin
desligado, storage inseguro e integracoes externas obrigatorias para operacao completa.
Ele valida configuracao tecnica por variaveis de ambiente; nao comprova politica de privacidade aprovada, contratos, encarregado, canais institucionais ou funcionamento real de notificacoes e backups. O prototipo atual nao passou por essas etapas operacionais.

## Gunicorn

```bash
FLASK_ENV=production gunicorn -c gunicorn.conf.py wsgi:app
```

### Logs operacionais e privacidade

O log de acesso do Gunicorn e o do Nginx registram apenas horário, método, status, tamanho e duração. Não acrescente IP, URL completa, query string, referer nem user agent aos formatos; esses valores podem conter dados pessoais ou credenciais. O mascaramento do logger Flask também cobre mensagens e tracebacks, mas não controla logs de erro do Nginx, journald, Docker, ferramentas externas ou arquivos antigos. Restrinja acesso e retenção desses logs no host antes de operar com dados reais. Confira os formatos com uma requisição de teste contendo um marcador na query string e verifique que ele não aparece nos logs. Referências de configuração: [Gunicorn](https://docs.gunicorn.org/en/stable/settings.html#access-log-format) e [Nginx](https://nginx.org/en/docs/http/ngx_http_log_module.html).

## Docker desenvolvimento

```bash
docker compose up --build
```

## Docker producao

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Nao use as senhas padrao do `docker-compose.yml` em producao.

## Healthchecks

- `/healthz`
- `/readyz`

## CI/CD

O workflow `Deploy` publica uma imagem identificada pelo commit, promove primeiro
para o GitHub Environment `staging` e somente depois para `production`. Configure
em cada Environment:

- secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` e `DEPLOY_KNOWN_HOSTS`; <!-- pragma: allowlist secret -->
- variables `APP_DIR` e `HEALTHCHECK_URL`;
- reviewers obrigatorios no Environment `production`.

O host deve estar autenticado no GHCR com permissao somente de leitura. O deploy
executa as migrations antes de iniciar os workers e restaura a imagem anterior
automaticamente quando o readiness de producao falha.

# Scheduler

O scheduler nunca deve ser habilitado nos workers Gunicorn. No Compose de producao ele roda no servico dedicado `scheduler`. Fora do Docker, execute apenas uma instancia:

```bash
SCHEDULER_ENABLED=true python -m flask --app wsgi:app run-scheduler
```

O job `verificar_auditoria` confere a cadeia de eventos a cada 24 horas nesse processo. Configure `ALERT_EMAIL` ou `ALERT_WEBHOOK_URL` com `ALERT_WEBHOOK_ALLOWED_HOSTS` para receber falhas; sem um canal, o heartbeat e o alerta ficam apenas no banco. Para conferir manualmente após deploy ou restore, execute `docker compose -f docker-compose.prod.yml exec -T app flask --app wsgi:app audit-verify`; qualquer inconsistência ou evento sem hash faz o comando retornar erro. Execute a migration `0045` antes de iniciar workers da nova versão; ela cria o histórico de incidentes e os triggers que bloqueiam atualização/exclusão desse histórico.

O job `monitorar_prazos_privacidade` roda no mesmo scheduler uma vez por dia. Ele gera alertas de pedidos de titulares vencidos ou próximos do prazo e de incidentes sem decisão de comunicação após 24 horas do conhecimento de afetação. Configure um canal de alerta e acompanhe a fila; esse monitoramento não executa direitos nem envia comunicações à ANPD ou aos titulares.

A migration `0046` cria o histórico de solicitações de titulares e campos de entrega. Execute `db upgrade` antes de iniciar workers com o novo modelo. Pedidos concluídos ou recusados antes da migração podem não ter canal/protocolo registrados: revise-os antes de tratá-los como evidência de atendimento.

A migration `0047` acrescenta método, protocolo e horário da conferência de identidade aos pedidos. Pedidos antigos permanecem com esses campos vazios; o sistema não cria prova retroativa. Execute `db upgrade` antes de subir a aplicação atualizada.

A migration `0048` acrescenta versão do aviso e referência da evidência ao histórico de consentimentos, além de triggers que impedem UPDATE/DELETE comuns. Registros anteriores mantêm esses campos vazios e não passam a comprovar consentimento por migração. Execute `db upgrade` antes de iniciar a aplicação atualizada e confira os triggers `trg_consent_no_update` e `trg_consent_no_delete`. A interface não oferece concessão administrativa; uma futura coleta direta precisa guardar a versão do aviso e a referência verificável da decisão.

A migration `0049` amplia campos de pedidos de titulares e incidentes para armazenar ciphertext, removendo o índice de e-mail em claro. A aplicação nova cifra esses campos e os snapshots novos do histórico. Execute `db upgrade` com a aplicação parada antes de iniciar workers novos. A migration preserva valores legados em claro, sem afirmar proteção retroativa; avalie-os separadamente antes de operar com dados reais. O downgrade é bloqueado porque a redução de colunas pode truncar ciphertext; use backup validado e um plano explícito de reversão.

Após `0049`, execute `flask --app wsgi:app privacy-encryption-audit --strict` no banco migrado. O comando mostra somente contagens por coluna, exige ausência de valores em claro e tenta autenticar/decriptar cada ciphertext com a chave atual; valores ilegíveis causam erro mesmo sem `--strict`. Não lê backups antigos nem prova que os dados são verdadeiros, completos ou têm base legal. Um resultado zero é uma condição técnica necessária para os campos cobertos.

A migration `0052` converte destinatário, payload JSON e último erro de `notifications` para campos cifrados e cifra os registros antigos na própria migração. Execute-a em janela de manutenção, com `SECRET_KEY` e `ENCRYPTION_SALT` originais e backup cifrado validado; a conversão de JSON para texto cifrado não tem downgrade seguro. Depois, `privacy-encryption-audit --strict` inclui essas três colunas. Backups anteriores à migration ainda podem conter esses dados em claro e precisam seguir sua própria retenção e proteção.

A migration `0055` alarga e cifra `user_sessions.ip_address`, `user_sessions.user_agent`, `order_signatures.signer_name` e `order_signatures.ip_address`. Ela preserva a leitura na tela de sessões e na OS por meio do ORM, mas o banco passa a guardar ciphertext. Execute com as chaves atuais e backup cifrado validado; não há downgrade seguro. Rode `privacy-encryption-audit --strict` depois e confirme também a contagem de linhas, pois zero campos em claro é uma verificação vazia se a tabela não tiver registros. A migração não altera backups antigos.

## Credenciais separadas do banco em produção

Defina `MYSQL_USER`/`MYSQL_PASSWORD` para a conta de migração e `APP_DB_USER`/`APP_DB_PASSWORD` para a conta de execução. Gere uma senha diferente, com pelo menos 24 caracteres e apenas caracteres seguros em URL (por exemplo, `python -c "import secrets; print(secrets.token_urlsafe(32))"`). O serviço `migrate` aplica migrations com a conta de migração. O serviço descartável `db-access` usa a credencial root apenas para criar/atualizar a conta de execução e conceder `SELECT`, `INSERT`, `UPDATE` e `DELETE` no banco configurado. `app` e `scheduler` aguardam esse serviço e usam somente a conta de execução. A conta de execução não deve ser usada para `db upgrade` nem para o `mysqldump` de triggers/rotinas.

Ao migrar uma instalação existente, adicione as duas variáveis `APP_DB_*` ao ambiente antes de subir a nova imagem. O provisionador recusa usar a mesma conta de `MYSQL_USER` ou `root` e falha se detectar concessões adicionais. Valide no ambiente de destino com `SHOW GRANTS FOR '<APP_DB_USER>'@'%'`, sem registrar o hash de senha exibido pelo MariaDB em logs compartilhados. A separação não protege contra a conta root, administradores do host ou comprometimento do serviço de migração; mantenha essas credenciais fora do processo web e em cofre de segredos.

Para backup cifrado do banco, agende `docker compose -f docker-compose.prod.yml --profile maintenance run --rm backup`. O serviço usa a conta de migração e grava no volume `backups_data`; configure a cópia externa e retenção desse volume conforme [Backup e restore](BACKUP_RESTORE.md). Ele não é iniciado automaticamente pelos workers nem pelo scheduler da aplicação.

O scheduler de produção monta `backups_data` e grava âncoras de verificação da auditoria nesse volume. O processo externo de cópia deve incluir arquivos `.audit-anchor.json` e usar `--require-audit-anchor`; confira que o destino possui a âncora antes de considerar a evidência independente. Falha de escrita da âncora faz o job de auditoria falhar e aciona o alerta operacional. O diretório do volume precisa permitir escrita pelo usuário `zokyo` do contêiner.

Para uploads locais, agende também `docker compose -f docker-compose.prod.yml --profile maintenance run --rm backup-storage`. Esse serviço monta `uploads_data` somente para leitura e publica apenas arquivos cifrados e metadados no mesmo volume de backups. A cópia externa, a retenção e o teste periódico de restore são tarefas do host; se S3 estiver ativo, configure backup próprio do bucket.

A chave `BACKUP_ENCRYPTION_KEY` é entregue apenas aos serviços de manutenção `backup` e `backup-storage`. `app`, `scheduler` e `migrate` não recebem essa chave. Se executar `production-check --strict-integrations` dentro de um contêiner `app` descartável, injete a chave apenas nessa execução, por exemplo com `docker compose -f docker-compose.prod.yml run --rm -e BACKUP_ENCRYPTION_KEY app flask --app wsgi:app production-check --strict-integrations`; mantenha a variável no ambiente do host, sem passá-la como valor na linha de comando.
