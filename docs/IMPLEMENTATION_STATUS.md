# Status de implementacao

Atualizado em 2026-07-11.

## Concluido com evidencia

- Diagnostico inicial do reposititorio: application factory em `app/__init__.py`, blueprints em `app/routes`, modelos em `app/models`, PDF legado em `app/utils/pdf_gen.py`, uploads de OS em `instance/uploads/os_fotos`, configuracoes de empresa em `Configuracao`, auditoria em `EventoLog`.
- Modulo de laudos integrado ao Flask: `app/models/laudo.py`, `app/services/laudos.py`, `app/routes/laudos.py` e registro em `app/__init__.py`.
- Navegacao principal com item "Laudos": `app/templates/partials/_sidebar.html`.
- Integracao com OS: `app/routes/pages.py` carrega laudos por OS e `app/templates/pages/os_detalhe.html` mostra a tabela relacionada.
- PDF no servidor: `finalizar_laudo()` gera PDF via ReportLab, calcula SHA-256 e grava em storage privado.
- Storage privado: arquivos em `instance/uploads/reports/<organization>/<uuid>/`.
- Fotos de laudo: entidade `LaudoFoto` com MIME, tamanho, dimensoes e hash; validacao por Pillow.
- Documentacao inicial: `docs/LAUDOS.md`.
- Testes automatizados iniciais: `python -m pytest -q` retornou `11 passed` em 2026-07-11.
- Validacao de templates: parser Jinja retornou `templates ok` em 2026-07-11.
- Compilacao Python: `python -m compileall app tests` executado com sucesso em 2026-07-11.
- Ruff inicial configurado em `pyproject.toml` para erros criticos e validado com `python -m ruff check app tests scripts`.
- Cobertura medida com `python -m coverage run -m pytest -q; python -m coverage report`: cobertura total atual 39%.
- Healthchecks adicionados: `/healthz` e `/readyz`, com testes automatizados.
- Tratamento de erros HTML/API separado para 403, 404, 405 e 500, com templates amigaveis e JSON para `/api/*`.
- Flask-Migrate registrado e `db.create_all()` desabilitado em producao.
- Estrutura Alembic criada em `migrations/` com migracao inicial do modulo de laudos.
- Dockerfile, `.dockerignore`, `docker-compose.yml` e `docker-compose.prod.yml` adicionados.
- Testes de upload valido e MIME falso para fotos de laudo adicionados.
- CI inicial criado em `.github/workflows/ci.yml` com compile, ruff, pytest, validacao de templates, scan simples de segredos e validacao Node.
- Dependabot criado em `.github/dependabot.yml`.
- `npm test` deixou de ser falso e agora executa `node --check wpp-server.js`; validado localmente em 2026-07-11.

## Pendente

- Remover dependencia operacional de `db.create_all()` tambem em desenvolvimento/testes depois do baseline Alembic completo.
- Criar baseline Alembic completo do schema legado alem da migracao de laudos.
- Criar suite ampla de testes de concorrencia, RBAC, isolamento multiempresa, PDF e uploads.
- Docker/Compose/CI/CD completos para producao.
- Multiempresa real com tenant obrigatorio.
- QR Code visual no PDF.
- Thumbnails separados e rotina de limpeza de arquivos orfaos.
- Recuperacao de senha, 2FA, Sentry, metricas e backup/restore testado.
- Revisao completa de CSP de producao e remocao de dependencias CDN no layout global.

## Bloqueado por decisao externa

- Escolha juridica de licenca.
- Definicao comercial de planos, cobranca e gateway.
- Politica de assinatura eletronica/digital e validade juridica desejada.
