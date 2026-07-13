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

Instalacoes novas executam o baseline completo automaticamente. Para um banco legado criado antes do Alembic, faca backup, confira o schema e marque o baseline antes do upgrade:

```bash
python -m flask --app wsgi:app db stamp 20260710_0000
python -m flask --app wsgi:app db upgrade
```

Nunca use `stamp` em banco vazio.

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

- secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` e `DEPLOY_KNOWN_HOSTS`;
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
