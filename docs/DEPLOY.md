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
python scripts/migrate_laudos.py
```

Enquanto o baseline Alembic completo do legado nao existir, mantenha tambem os scripts idempotentes em `scripts/`.

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

## Scheduler

Atualmente o scheduler de limpeza de rate limit ainda inicia no processo Flask. Para producao com multiplos workers, a pendencia e mover tarefas agendadas para worker/cron separado.
