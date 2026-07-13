# Status de implementacao

Atualizado em 2026-07-12.

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
- Permissao por documento em laudos: tecnico operacional so altera/finaliza laudos criados, atribuidos ou atualizados por ele; administradores mantem acesso total.
- CSP de producao endurecida: `connect-src` nao libera `localhost`/WebSocket local quando cookies seguros de producao estao ativos.
- Conteudo textual do PDF de laudo escapado antes de renderizar no ReportLab.
- Testes automatizados: `python -m pytest -q` retornou `36 passed` em 2026-07-12.
- Compilacao Python: `python -m compileall app tests` executado com sucesso em 2026-07-12.
- Ruff: `python -m ruff check app tests scripts` retornou `All checks passed!` em 2026-07-12.
- Fotografias de laudos agora possuem thumbnail privado otimizado, EXIF removido, reordenacao validada no backend e comando `laudos storage-audit` para detectar/remover arquivos orfaos.
- PDF inclui QR Code local de verificacao; valores textuais e tabelas sao escapados antes do ReportLab.
- Storage endurecido contra traversal por verificacao estrutural de caminho e finalizacao remove PDF movido caso a transacao falhe.
- Migracao incremental `20260712_0002` adiciona `thumbnail_key` sem recriar tabelas.
- Cobertura medida com `python -m coverage run -m pytest -q; python -m coverage report`: total 54%, servico de laudos 82% e modelos de laudos 97%.
- Scheduler desativado por padrao nos workers e isolado no servico `scheduler` do Compose de producao com `SCHEDULER_ENABLED=true` apenas nesse processo.
- Baseline Alembic completo `20260710_0000` validado em banco SQLite vazio; `db check` nao detectou divergencias e o Compose executa `migrate` antes da aplicacao.
- Recuperacao de senha com token de uso unico armazenado como SHA-256, expiracao, invalidacao, anti-enumeracao, rate limit, SMTP opcional e testes do ciclo completo.
- Login redesenhado sem metricas demonstrativas falsas e sem fonte/CDN externa.
- Testes de login, logout, CSRF e bloqueio de usuario inativo adicionados.
- Logs JSON em producao com mascaramento e `X-Request-ID`; metricas Prometheus protegidas em `/metrics` e Sentry opcional sem PII padrao.
- Backup do storage privado com manifesto SHA-256, verificacao sem extracao, restauracao segura contra traversal e teste byte a byte.
- Backup do banco agora registra SHA-256 no metadata sidecar.
- Google Fonts/CDNs removidos dos templates e da CSP; scripts e fontes ficam restritos a recursos locais.
- 2FA TOTP administrativo implementado com segredo criptografado, desafio pos-senha, ativacao confirmada, desativacao com senha+TOTP e codigos de recuperacao de uso unico.
- Migracao `20260712_0004` adiciona os campos de 2FA sem armazenar segredo ou codigos em texto puro.
- RBAC central com matriz, decorator, permissoes atomicas e overrides persistidos por usuario; perfil legado `tecnico` removido das rotas de estoque.
- Multiempresa incremental no nucleo: `Organization`, backfill padrao e `organization_id` obrigatorio em usuarios, clientes, OS e laudos.
- Escopo ORM central de tenant e filtros explicitos em laudos, fotos e usuarios; teste de IDOR entre organizacoes retorna 404.
- Migracoes `20260712_0005` e `20260712_0006` cobrem overrides RBAC e tenant core.
- CI configurado para aplicar toda a cadeia Alembic em MariaDB 11 limpo, alem dos testes SQLite.
- Tenant propagado para estoque, fornecedores, financeiro, configuracoes, auditoria, coletas, fotos de OS, historicos, defeitos e eventos/fotos de laudo pela migracao `20260712_0007`.
- `Configuracao` deixou de usar ID singleton global e passou a ser unica por organizacao.
- Teste central comprova leitura isolada e atribuicao automatica de tenant em configuracoes e estoque.
- CLI `create-organization` provisiona organizacao, configuracao e administrador em uma transacao auditada; teste automatizado cobre o fluxo.
- Logging tornou-se idempotente entre factories/workers e evita SQL detalhado sem `SQLALCHEMY_ECHO` explicito.
- Restore de banco verifica sidecar, tamanho e SHA-256 antes de executar; credenciais usam arquivo temporario e o teste rejeita backup corrompido.
- CI inicial criado em `.github/workflows/ci.yml` com compile, ruff, pytest, validacao de templates, scan simples de segredos e validacao Node.
- Dependabot criado em `.github/dependabot.yml`.
- `npm test` valida a sintaxe de todo JavaScript estatico e da configuracao Playwright.
- Docker Compose validado localmente com MariaDB 11 e aplicacao saudaveis em `http://127.0.0.1:8000`.
- Cadeia Alembic aplicada no MariaDB ate `20260712_0007`; `flask db check` retornou `No new upgrade operations detected`.
- Dependencia implicita de `db.create_all()` removida da factory; ambientes reais usam exclusivamente migrations Alembic.
- Auditoria Playwright executou 30 cenarios desktop/mobile sem erro de console, HTTP 5xx, overflow horizontal ou violacao seria WCAG A/AA.
- RBAC atomico corrigido nas rotas de finalizar, revisar e baixar PDF de laudo; overrides negativos agora sao aplicados no backend.
- Laudo cancelado possui comprovante PDF separado e auditado, sem sobrescrever o PDF originalmente emitido.
- Listagem de laudos possui exportacao CSV filtrada por tenant, com neutralizacao de CSV injection.

## Pendente

- Nenhuma implementacao interna obrigatoria do roadmap permanece pendente.
- Itens opcionais e decisoes externas estao registrados em `ROADMAP_PROFISSIONAL.md`.

## Bloqueado por decisao externa

- Escolha juridica de licenca.
- Definicao comercial de planos, cobranca e gateway.
- Politica de assinatura eletronica/digital e validade juridica desejada.

## Riscos conhecidos

- O WPPConnect embutido foi removido porque sua versao atual mantinha dependencias vulneraveis. O envio manual permanece disponivel e o modo automatico aceita somente gateway externo HTTPS, autenticado e em allowlist.
- O ambiente local usa `ENCRYPTION_SALT` de desenvolvimento. Producao exige segredo aleatorio proprio.

## Entregas finais de 2026-07-12

- Concorrencia de numeracao validada no MariaDB com 24 reservas simultaneas, todas unicas e sequenciais.
- Backup e restore completos validados em banco MariaDB descartavel; dump portavel e rejeicao de comandos de troca/exclusao de database.
- Compose de producao testado ponta a ponta com Nginx, app, scheduler, migracoes e healthcheck; WhatsApp isolado em perfil opcional.
- Templates de laudo versionados, requisitos fotograficos configuraveis e snapshot imutavel no PDF.
- Portal publico minimo com token armazenado por hash e decisao idempotente de orcamento.
- Relatorios filtrados por tenant em tela, CSV, XLSX e PDF, incluindo protecao contra formula injection.
- Painel global SaaS, planos, limites, assinatura e webhook sandbox assinado e idempotente.
- Controles LGPD operacionais: consentimento, solicitacao, ZIP estruturado e anonimizacao conservadora.
- Fila de notificacoes WhatsApp na migracao `20260712_0012`, com chave idempotente, historico, retry exponencial e estados terminais.
- CSP HTTP removeu `unsafe-inline` de `style-src`; estilos dinamicos foram substituidos por classes e blocos publicos usam nonce.
- Validacao final: 69 testes Python, Ruff e compilacao aprovados; cobertura total medida em 61%, servico de laudos em 84% e notificacoes em 94%.
- Auditoria Playwright autenticada aprovada em 40 cenarios desktop/mobile, sem erro da aplicacao, HTTP 5xx, overflow horizontal ou violacao seria WCAG A/AA.
- MariaDB local esta na revisao `20260712_0015`, `flask db check` nao encontrou divergencias e `/healthz` respondeu HTTP 200.
- Instalacao nova possui `seed-system` idempotente para planos globais; administradores possuem historico paginado da fila de notificacoes, filtros e reenvio isolado por tenant.
- Onboarding individual para novas contas administrativas, checklist real e Central de Ajuda permanente.
- Retencao por tenant na migracao `20260712_0014`: prazos por categoria, aprovacao registrada, inativa por padrao e limitada a tokens sem uso e notificacoes terminais.
- Roadmap interno zerado; decisoes nao tecnicas foram separadas em `DECISOES_EXTERNAS.md`.
- Revisao geral removeu codigo/assets orfaos, documentacao duplicada, entrypoints sem uso e o caminho vulneravel de `pdfkit`/wkhtmltopdf.
- PDF de OS consolidado em ReportLab com escape de markup e teste de regressao.
- Clientes e fornecedores agora sao arquivados sem apagar historico; pecas usadas em OS nao podem ser excluidas.
- Validacao explicita impede vinculos de fornecedor/OS entre tenants; perfil Consulta possui testes negativos de mutacao.
- Dependencias Python auditadas sem vulnerabilidades conhecidas; lint estrutural ampliado e CI com Bandit, pip-audit e detect-secrets.
- Validacao final da revisao: 72 testes Python, cobertura total de 62%, 40 cenarios Playwright e 146 regras Flask sem duplicidade.
- `pip-audit` e `npm audit` nao encontraram vulnerabilidades conhecidas nas dependencias instaladas.
- Backups podem ser criptografados em fluxo com AES-256-GCM; adulteracao e truncamento sao rejeitados e testados.
- Contas possuem `security_version`: troca de senha e revogacao administrativa encerram todas as sessoes anteriores imediatamente.
- 2FA administrativo e obrigatorio por padrao em producao por `REQUIRE_ADMIN_2FA=true`.
- Relatorios exibem margem estimada, tempo medio, conversao de orcamento, OS em garantia e clientes recorrentes/inativos.
- CI diario valida migrations e drift no MariaDB e bloqueia imagem Docker com vulnerabilidades conhecidas altas ou criticas.
- Plano de desastre, RPO, RTO, restauracao trimestral e rollback documentados em `docs/DISASTER_RECOVERY.md`.
- Sessoes persistentes por dispositivo com IP, user-agent, atividade, revogacao individual/global e invalidacao por versao de seguranca.
- Estoque com livro de movimentos, justificativa, reservas por OS, consumo/estorno e sugestoes de compra.
- Financeiro com parcelamento, recorrencia mensal, conciliacao, comissoes, DRE e exportacao contabil protegida.
- Atendimento com checklists versionados, snapshot na OS, aceite do termo no PDF e vinculo de retorno em garantia.
- Comunicacao com templates versionados, SMTP na fila persistente e notificacoes de mudanca de status.
- SaaS com convites de uso unico, branding por tenant e metricas de usuarios, clientes, OS, storage e atividade.
- Filtros salvos, relatorios agendados no scheduler, teste de carga no CI e release auditada por tag semantica.
- Validacao atual: 97 testes Python, cobertura global de 66%, nucleo de dominio/servicos em 88%, 165 cenarios Playwright em cinco viewports (160 aprovados e 5 nao aplicaveis por modo de navegacao) e Alembic `20260712_0026` sem drift.
