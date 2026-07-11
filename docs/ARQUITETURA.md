# Arquitetura

O Zokyo usa Flask com application factory em `app/__init__.py`.

## Camadas

- `app/models`: modelos SQLAlchemy.
- `app/routes`: blueprints HTML e API.
- `app/services`: regras de negocio mais longas.
- `app/utils`: seguranca, PDF, WhatsApp, validadores e auxiliares.
- `app/templates`: Jinja2.
- `app/static`: CSS/JS/imagens publicas.
- `instance/uploads`: arquivos privados.

## Entry points

- Desenvolvimento: `python app.py`.
- WSGI/CLI: `wsgi:app`.
- Gunicorn: `gunicorn -c gunicorn.conf.py wsgi:app`.

## Banco

Flask-Migrate foi registrado em `app/extensions.py` e `app/__init__.py`. Em producao, `db.create_all()` fica desabilitado por `ProductionConfig.DISABLE_CREATE_ALL = True`.

Pendencia: baseline Alembic completo do schema legado.

## Laudos

Laudos ficam em:

- modelo: `app/models/laudo.py`;
- servico: `app/services/laudos.py`;
- rotas: `app/routes/laudos.py`;
- storage privado: `instance/uploads/reports`.
