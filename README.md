# Zokyo

Sistema multiempresa para assistencias tecnicas, desenvolvido com Flask, SQLAlchemy e MariaDB. Inclui clientes, ordens de servico, estoque, financeiro, laudos tecnicos, PDFs, portal do cliente, relatorios, PWA, WhatsApp opcional, RBAC, 2FA, LGPD operacional e preparacao SaaS.

## Inicio rapido com Docker

Requisitos: Docker Desktop com Compose.

```bash
docker compose up -d --build
docker compose run --rm app flask --app wsgi:app db upgrade
docker compose run --rm app flask --app wsgi:app seed-system
```

Abra `http://127.0.0.1:8000`. Na primeira instalacao, use a tela de primeiro acesso para criar a organizacao e o administrador.

Verifique o ambiente:

```bash
docker compose ps
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/readyz
```

## Desenvolvimento sem Docker

Requisitos: Python 3.11+, MariaDB 11 e Node.js 20 apenas para WhatsApp/E2E.

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements-dev.txt
copy .env.example .env
flask --app wsgi:app db upgrade
flask --app wsgi:app seed-system
flask --app wsgi:app run --debug
```

No Linux/macOS, ative o ambiente com `source .venv/bin/activate` e copie o arquivo com `cp`.

## Configuracao

Use `.env.example` em desenvolvimento e `.env.production.example` como referencia de producao. Nunca versione `.env`, tokens, bancos, uploads ou logs de importacao.

Obrigatorias em producao:

- `FLASK_ENV=production`
- `SECRET_KEY` aleatoria e persistente
- `DATABASE_URL`
- `ENCRYPTION_SALT` aleatorio em Base64

Consulte [Configuracao](docs/CONFIGURACAO.md), [Deploy](docs/DEPLOY.md) e [Seguranca](docs/SEGURANCA.md).

## Banco e migrations

O schema e gerenciado exclusivamente pelo Alembic. Nao execute `db.create_all()` nem scripts SQL manuais em ambientes reais.

```bash
flask --app wsgi:app db upgrade
flask --app wsgi:app db current
flask --app wsgi:app db check
```

Instalacoes novas executam a cadeia Alembic iniciada pela baseline consolidada em `migrations/versions/`, seguida das evolucoes incrementais.

## Testes e qualidade

Estado verificado em 2026-08-27: 201 testes Python aprovados, 200 cenários Playwright executados nos projetos compact, mobile, tablet, desktop e wide, e teste local de 150 requisições simultâneas sem erro. A auditoria E2E autenticada exige uma conta fictícia no ambiente de teste.

```bash
pytest -q
ruff check app tests scripts
python -m compileall -q app tests scripts
npm test
```

Auditoria visual autenticada:

```bash
set E2E_EMAIL=admin@empresa.com
set E2E_PASSWORD=senha-de-teste
npm run test:e2e
```

Os testes nunca devem usar credenciais ou mensagens reais.

## Producao

O Compose de producao possui MariaDB, migracao controlada, Gunicorn, scheduler dedicado e Nginx. O WhatsApp usa link manual seguro ou um gateway HTTPS externo autenticado.

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Configure HTTPS no proxy externo e segredos fora do reposititorio. Consulte [Deploy](docs/DEPLOY.md), [Backup e restore](docs/BACKUP_RESTORE.md) e [Observabilidade](docs/OBSERVABILIDADE.md).

## Estrutura

- `app/models`: entidades e constraints ORM.
- `app/routes`: blueprints HTML e API.
- `app/services`: regras de negocio e integracoes.
- `app/templates`, `app/static`: interface e PWA.
- `migrations`: cadeia Alembic.
- `scripts`: backup, restore, auditoria e testes operacionais.
- `tests`: testes unitarios, integracao e Playwright.
- `docs`: arquitetura, rotas, permissoes e operacao.

## Documentacao

- [Arquitetura](docs/ARQUITETURA.md)
- [Laudos](docs/LAUDOS.md)
- [API](docs/API.md)
- [Rotas](docs/ROTAS.md)
- [Permissoes](docs/PERMISSOES.md)
- [SaaS e LGPD](docs/SAAS.md)
- [Checklist de go-live](docs/GO_LIVE.md)
- [Política de suporte e operação](docs/SUPORTE_OPERACAO.md)
- [Backup e restore](docs/BACKUP_RESTORE.md)
- [Recuperação de desastre](docs/DISASTER_RECOVERY.md)
- [Observabilidade](docs/OBSERVABILIDADE.md)
- [Pendencias atuais](oque_falta.md)
- [Decisoes externas](docs/DECISOES_EXTERNAS.md)

A licenca juridica ainda depende de decisao do proprietario. Nao presuma permissao de redistribuicao ate essa definicao.
