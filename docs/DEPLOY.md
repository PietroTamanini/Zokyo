# Deploy

## Variaveis

Use `.env.production.example` como base. Em producao sao obrigatorias:

- `FLASK_ENV=production`
- `SECRET_KEY`
- `DATABASE_URL`
- `ENCRYPTION_SALT`

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
desligado e integracoes externas obrigatorias para operacao completa.

## Gunicorn

```bash
FLASK_ENV=production gunicorn -c gunicorn.conf.py wsgi:app
```

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
