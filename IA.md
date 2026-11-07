# Memória técnica do Zokyo para IAs

Este é o documento de continuidade do projeto. Toda IA que trabalhar neste repositório deve lê-lo antes de alterar código, banco, infraestrutura ou documentação. Ele não substitui os documentos especializados em `docs/`; serve como mapa, histórico curto e conjunto de invariantes para evitar retrabalho e regressões.

Última atualização: 2026-11-02.

## Objetivo do produto

O Zokyo é uma plataforma multiempresa para assistências técnicas. Centraliza clientes, ordens de serviço, bancada, estoque, financeiro, laudos, coleta/entrega, portal do cliente, relatórios, comunicação e operação SaaS.

O objetivo atual não é acumular módulos. A prioridade é transformar a implementação existente em um produto simples, confiável e seguro para uso diário, primeiro em piloto controlado e depois em produção comercial.

## Estado resumido

- Aplicação Flask, MariaDB, Redis e site público executam em Docker local com healthchecks saudáveis.
- Schema gerenciado por Alembic até a migration `20261102_0038`.
- O isolamento multiempresa usa escopo ORM, bloqueio de mutacoes cruzadas, filtros explicitos em SQL manual e integridade referencial; MariaDB nao possui RLS nativo.
- 200 cenários Playwright executados em compact, mobile, tablet, desktop e wide.
- Auditoria visual cobre overflow, runtime, HTTP 500 e violações WCAG sérias.
- Teste local de 150 requisições simultâneas passou após correção do rate limit persistente.
- Em 2026-11-02, 334 testes Python passaram; compilação Python e validação JavaScript também passaram.
- Auditorias de dependências passaram na revisão anterior.
- O código está apto para piloto controlado, mas o ambiente comercial ainda não foi homologado.
- Em 2026-09-23, `production-check --strict-integrations` foi executado no Compose local e reprovou somente por configuração externa ausente: `FLASK_ENV=production`, URL HTTPS pública, métricas, chave de backup, alertas, SMTP e WhatsApp automático. Redis, `SECRET_KEY`, `ENCRYPTION_SALT` e `BLIND_INDEX_KEY` locais já estão configurados com valores dev-only válidos; segredos reais de produção ainda precisam ser provisionados fora do Git.
- Em 2026-09-23, o Compose de desenvolvimento passou a subir Redis (`redis://redis:6379/0`) para exercitar sessões e rate limit distribuído localmente.
- Em 2026-09-23, o Compose de desenvolvimento passou a definir `SECRET_KEY`, `ENCRYPTION_SALT` e `BLIND_INDEX_KEY` dev-only válidos; sem isso, `create-organization` e fluxos que calculam índice cego falhavam no Gunicorn local.
- Em 2026-11-02, a cadeia Alembic foi aplicada até `20261102_0038`, incluindo configurações da plataforma, onboarding, caixa, inventário físico e alinhamento de defaults do schema.
- Ao final da sessão de 2026-09-24, app, MariaDB, Redis e site público estavam saudáveis no Compose; `/healthz`, `/readyz`, o site público e `redis-cli ping` responderam com sucesso em `http://127.0.0.1:8000` e `http://127.0.0.1:5500`.

Consulte [docs/ESTADO_ATUAL.md](docs/ESTADO_ATUAL.md), [oque_falta.md](oque_falta.md) para o checklist atual e [CHANGELOG.md](CHANGELOG.md) para a evolução versionada.

## Tecnologias

### Backend

- Python 3.11 como versão de referência em Docker e CI.
- Flask 3, Flask-SQLAlchemy e SQLAlchemy 2.
- Flask-Migrate/Alembic para schema.
- MariaDB 11 em desenvolvimento integrado e produção.
- Redis 7 em Docker local e produção para sessões e rate limit distribuído, com fallback seguro para MariaDB no rate limit.
- SQLite em memória apenas nos testes unitários apropriados.
- Gunicorn com workers síncronos em produção.
- ReportLab para PDFs.
- APScheduler em processo dedicado.
- Cryptography para campos e backups sensíveis.

### Frontend

- HTML/Jinja, CSS e JavaScript sem framework SPA.
- Interface responsiva e PWA.
- Playwright e axe-core para E2E, responsividade e acessibilidade.
- Site institucional separado em `dj-tech/`, servido localmente na porta 5500.

### Operação

- Docker Compose para desenvolvimento e produção.
- Nginx no Compose de produção.
- GitHub Actions para CI, release, imagem, staging e produção.
- Prometheus e Grafana em `monitoring/`.
- Sentry opcional.
- Scripts próprios de backup, criptografia, envio externo, restore e carga.

## Estrutura do repositório

- `app/models/`: entidades, relacionamentos, constraints e auditoria.
- `app/routes/`: páginas HTML e APIs organizadas por blueprint.
- `app/services/`: regras reutilizáveis, integrações, laudos, notificações e importação.
- `app/templates/`: telas Jinja.
- `app/static/`: CSS, JavaScript, imagens e PWA.
- `migrations/`: única fonte válida para evolução do schema real.
- `tests/`: testes unitários, integração, contratos e Playwright.
- `scripts/`: backup, restore, carga e verificações operacionais.
- `monitoring/`: Prometheus, alertas e Grafana.
- `dj-tech/`: site público e consulta de OS.
- `docs/`: documentação especializada.

## Módulos implementados

- Autenticação, recuperação de senha, sessões revogáveis e 2FA TOTP.
- Organizações, assinaturas, planos, limites e isolamento multiempresa.
- Usuários, cargos, permissões RBAC/ABAC e convites.
- Clientes, fornecedores, produtos/peças e serviços.
- Ordens de serviço, kanban, bancada, checklist, fotos e assinatura simples.
- Orçamento, aprovação pelo cliente, pagamentos parciais, baixa e garantia.
- Laudos com templates, rascunho, revisão, finalização, PDF, hash e storage privado.
- Estoque, lotes, movimentações, mínimos, fornecedores e compras sugeridas.
- Financeiro, caixa, receitas, despesas, cobranças, conciliação e relatórios.
- Agenda, coleta, entrega, múltiplos pontos, rota e comprovantes.
- Portal do cliente e consulta pública integrada ao site.
- Notificações, templates versionados, retry e fallback `wa.me`.
- Histórico das mensagens de cada OS e reenvio contextual preservando as tentativas anteriores.
- Logs de auditoria, métricas, healthchecks, alertas e retenção LGPD.
- Importação de bancos externos, incluindo legado Firebird.

## Regras que não podem ser quebradas

1. Nunca usar `db.create_all()` em instalação ou produção. O schema real evolui somente por Alembic.
2. Toda consulta e mutação de dado empresarial deve respeitar `organization_id` e o tenant da sessão.
3. SQL manual (`text()`) nao recebe o escopo automatico do ORM e deve filtrar `organization_id` explicitamente.
4. Perfis sem permissão não podem obter dados sensíveis nem por API nem por página HTML.
5. Técnico não recebe acesso financeiro sensível por padrão; atendente não altera configuração crítica.
6. OS não pode ser finalizada/entregue sem pagamento integral conforme a regra atual.
   A edição da OS também deve bloquear a entrega; nunca criar recebimento implícito apenas pela mudança de status.
7. Arquivamento deve preservar histórico; não transformar exclusão lógica em remoção destrutiva acidental.
8. Produto ou serviço inativo não pode entrar em nova OS.
9. Movimentação de peça usada na OS deve manter estoque e histórico consistentes.
10. Observação interna não pode vazar para o portal do cliente.
11. PDFs, uploads, fotos, assinaturas e laudos privados exigem autorização e isolamento do tenant.
12. Tokens, documentos, e-mails e segredos não devem aparecer integralmente em logs.
13. A assinatura atual é simples e não deve ser apresentada como certificação ICP-Brasil.
14. Rate limits persistentes precisam continuar seguros com múltiplos workers. No MariaDB, o contador global usa upsert atômico e retry limitado para erros transitórios 1020, 1205 e 1213.
15. O scheduler deve rodar em processo dedicado, nunca duplicado em cada worker Gunicorn.
16. Segredos reais, bancos, uploads, dumps e arquivos `.env` não entram no Git.

## Decisões técnicas importantes

- MariaDB é o banco de produção; compatibilidade SQLite existe para acelerar testes, não para definir comportamento de produção.
- O Compose de desenvolvimento usa credenciais deliberadamente locais e não reutilizáveis em produção.
- O site público chama a API do painel; origens permitidas precisam ser explícitas.
- PDFs de OS e laudos usam ReportLab; não reintroduzir wkhtmltopdf/pdfkit sem necessidade comprovada.
- O WhatsApp automático deve usar apenas a Meta WhatsApp Cloud API oficial; fallback manual por `wa.me` permanece seguro.
- Backups devem sair do host, ser criptografados e ter restore comprovado.
- Imagens de produção devem ser imutáveis e identificadas pelo commit/tag.
- Aliases de rotas legadas permanecem por compatibilidade; remover apenas com plano de migração e testes.

## Correção recente que merece atenção

Em 2026-08-27, a auditoria E2E concorrente revelou HTTP 500 no MariaDB: workers atualizavam o mesmo registro de `api_rate_limits`. A solução em `app/utils/rate_limit.py` usa `INSERT ... ON DUPLICATE KEY UPDATE` e retry curto somente para conflitos transitórios reconhecidos. Há cobertura em `tests/test_operational_utils_contracts.py`.

Ao alterar rate limit, middleware global, pool de conexões ou configuração Gunicorn, repetir teste real concorrente; testes SQLite isolados não são suficientes para essa área.

Em 2026-09-03, a consolidação financeira por OS foi coberta por testes dedicados. O lucro usa faturamento da OS menos custo histórico das peças, custo de mão de obra (`horas_trabalho * custo_hora`) e comissões pagas de receitas. Cobranças pendentes vencidas aceitam datas do banco sem fuso e horário atual UTC sem gerar erro de comparação. O resumo da tela acompanha o intervalo selecionado, não necessariamente o mês corrente.

Eventos de OS são enfileirados por `app/services/order_notifications.py`. Criação pelo painel/API/coleta, mudança de status, aprovação de orçamento, faturamento pendente e retorno em garantia usam chaves idempotentes. Em rotas públicas, templates e configurações devem ser buscados pelo `organization_id` explícito da OS; nunca depender de tenant de sessão inexistente.

Desde a migration `20260924_0025`, notificações originadas por eventos de OS carregam `os_id`. A tela da OS lista as 20 mensagens mais recentes e o reenvio contextual cria uma nova entrada na fila, sem sobrescrever a tentativa anterior. Toda busca e todo reenvio validam simultaneamente `organization_id` e `os_id`.

O detalhe da OS reutiliza o mesmo cálculo financeiro consolidado da tela financeira para alertar lucro projetado negativo. A entrega com prejuízo exige confirmação explícita tanto no painel quanto na API (`confirm_loss_risk`), e essa confirmação é registrada de forma resumida no `EventoLog`. O alerta não substitui a regra de pagamento integral; ambas as validações permanecem obrigatórias.

Em 2026-09-03, o CI falhava antes de testar o produto por dois erros de infraestrutura: importação do script concorrente fora da raiz e tag inexistente do Trivy. O workflow executa o script como módulo e fixa `trivy-action` por SHA. Ao atualizar Actions, confirmar a referência publicada e preferir SHA imutável para ferramentas de segurança.

O scan seguinte expôs vulnerabilidades HIGH nas bibliotecas vendorizadas das ferramentas de build da imagem base. O `Dockerfile` atualiza essas ferramentas, instala o lock e remove `pip`, `setuptools` e `wheel` da imagem final, pois não são necessários em runtime. Não reduzir a severidade nem ignorar CVEs apenas para deixar o workflow verde; remover ou atualizar a camada vulnerável e confirmar no Trivy.

O CI Python precisa instalar `requirements-prod.lock` e `requirements-dev.txt`: a suíte usa ferramentas de desenvolvimento, enquanto o smoke de carga valida o servidor Gunicorn real. A etapa confirma `/healthz` antes de iniciar carga e deve falhar cedo se o processo não subir.

O `gunicorn.conf.py` aceita `GUNICORN_ACCESSLOG`, `GUNICORN_ERRORLOG` e `GUNICORN_PIDFILE`. A imagem usa diretórios persistentes preparados pelo Dockerfile; o CI usa stdout/stderr e `/tmp`.

Em 2026-09-15, o CRUD financeiro da API passou a registrar `EventoLog` em criacao, edicao e exclusao. Os eventos usam o tenant autenticado e descrevem somente ids, tipo/status e operacao; nao copiar `Transacao.descricao` nem outros campos livres para evitar vazamento de documentos, tokens ou segredos digitados pelo usuario.

Na mesma revisao, os fluxos centrais da API de OS passaram a espelhar eventos gerais em `EventoLog`: criacao, edicao, exclusao logica, vinculo/remocao de pecas e criacao/cancelamento de reservas. Manter os detalhes operacionais em `OSHistorico`, `InventoryMovement` e `StockReservation`; o log geral deve permanecer resumido e sem `defeito_alegado`, `observacoes` ou textos livres de servicos.

A API de estoque tambem espelha `EventoLog` para edicao, exclusao direta, ajuste e recebimento de lote. Justificativas de inventario/compra continuam em `InventoryMovement`; no evento geral registrar apenas ids e quantidades para reduzir risco de dados sensiveis em auditoria ampla.

Privacidade e relatorios salvos tambem foram cobertos em 2026-09-15. `ConsentRecord` e `DataSubjectRequest` seguem como trilhas de dominio, com espelho resumido em `EventoLog`; nao registrar nome, CPF/CNPJ, e-mail, nome livre de relatorio nem destinatario. Relatorios salvos registram apenas id e frequencia.

Billing/plataforma tambem ganhou espelho administrativo em `EventoLog`: criacao de plano, atribuicao manual de assinatura, checkout/cancelamento Asaas e webhooks sandbox/Asaas processados. `BillingEvent.payload` permanece a trilha detalhada; `EventoLog` deve conter somente tipo, status, plan_id, event_id interno do evento e tenant afetado, sem documento do assinante, tokens, payload completo, checkout URL ou external_id de gateway.

As lacunas automatizaveis da matriz central de auditoria foram fechadas em 2026-09-15. Recuperacao/reset de senha, aceite de convite, troca de senha pela API e regeneracao de token possuem eventos seguros; nao registrar e-mail, token bruto, senha, codigo de recuperacao ou nome livre nesses fluxos. As pendencias restantes da matriz sao homologacoes externas ou decisoes fora do repositorio.

O portal publico registra evento de seguranca para decisao de orcamento negada quando o token e valido mas a acao nao pode ser aplicada. Nao registrar token bruto nem detalhes internos da OS; token inexistente/expirado continua retornando 404 sem evento por nao haver tenant confiavel.

## Como executar

### Docker local

```bash
docker compose up -d --build
docker compose run --rm app flask --app wsgi:app db upgrade
docker compose run --rm app flask --app wsgi:app seed-system
```

- Painel: `http://127.0.0.1:8000`
- Site: `http://127.0.0.1:5500`
- Saúde: `http://127.0.0.1:8000/healthz`
- Prontidão: `http://127.0.0.1:8000/readyz`

Para desligar sem apagar banco/uploads:

```bash
docker compose down
```

Não use `docker compose down -v` sem autorização explícita, pois remove os volumes.

### Qualidade e testes

```bash
pytest -q
ruff check app tests scripts
python -m compileall -q app tests scripts
npm test
```

Auditoria autenticada:

```bash
set E2E_EMAIL=admin@empresa.com
set E2E_PASSWORD=senha-de-teste
npm run test:e2e
```

Use somente organização, usuários e mensagens fictícios em testes.

### Produção

```bash
docker compose -f docker-compose.prod.yml up -d --build
flask --app wsgi:app production-check --strict-integrations
```

O production check precisa passar sem erro. Consulte [CONFIGURACAO.md](docs/CONFIGURACAO.md), [DEPLOY.md](docs/DEPLOY.md) e [GO_LIVE.md](docs/GO_LIVE.md).

## Pendências prioritárias

1. Configurar staging/produção com segredos, domínio, HTTPS e 2FA administrativo.
2. Configurar SMTP, alertas e WhatsApp real.
3. Agendar backup externo criptografado e comprovar restore.
4. Homologar abertura de OS, busca de cliente, financeiro e PDFs com usuários reais.
5. Aprovar templates de mensagens para cada evento de OS.
6. Completar matriz formal de auditoria das mutações.
7. Revisar português, dark mode e formulários longos em aparelhos reais.
8. Definir licença, preços, gateway, SLA, LGPD e assinatura jurídica.
9. Executar piloto controlado antes de venda ampla.

## Documentos de referência

- [README](README.md): instalação e visão geral.
- [Pendências](oque_falta.md): checklist atualizado de conclusão.
- [Arquitetura](docs/ARQUITETURA.md): camadas e decisões estruturais.
- [API](docs/API.md) e [Rotas](docs/ROTAS.md): interfaces disponíveis.
- [Permissões](docs/PERMISSOES.md) e [Segurança](docs/SEGURANCA.md): controles de acesso.
- [Matriz de auditoria](docs/AUDITORIA_MUTACOES.md): cobertura de mutações, trilhas especializadas e lacunas priorizadas.
- [SaaS](docs/SAAS.md): multiempresa, planos e LGPD.
- [Laudos](docs/LAUDOS.md): domínio técnico e storage.
- [Backup e restore](docs/BACKUP_RESTORE.md) e [recuperação de desastre](docs/DISASTER_RECOVERY.md).
- [Observabilidade](docs/OBSERVABILIDADE.md).
- [Checklist de go-live](docs/GO_LIVE.md).
- [Homologação e evidências](docs/HOMOLOGACAO_EVIDENCIAS.md).
- [Suporte e operação](docs/SUPORTE_OPERACAO.md).
- [Decisões externas](docs/DECISOES_EXTERNAS.md).

## Protocolo para a próxima IA

1. Ler este arquivo, `README.md`, `oque_falta.md` e os documentos ligados à tarefa.
2. Verificar `git status` antes de agir e preservar alterações do usuário.
3. Rodar o sistema ou testes proporcionais antes de assumir que algo funciona.
4. Corrigir causa raiz e adicionar regressão quando encontrar defeito reproduzível.
5. Não marcar pendência externa como concluída sem evidência real.
6. Atualizar este arquivo quando mudar arquitetura, stack, regra crítica, estado verificado ou prioridade.
7. Atualizar `CHANGELOG.md` para mudanças relevantes ao produto.
8. Atualizar `oque_falta.md` quando uma pendência for concluída ou reclassificada.
9. Validar links Markdown e executar `git diff --check` antes de entregar documentação.
10. Relatar claramente o que foi alterado, testado, não testado e o que depende do proprietário.

## Limites de autonomia

Não escolher automaticamente licença, preços, provedor de cobrança, política jurídica, SLA, controlador LGPD, retenção definitiva ou natureza legal da assinatura. Essas decisões pertencem ao proprietário e aos responsáveis comercial/jurídico/operacional.

Não publicar, apagar volumes, restaurar dados, alterar produção ou usar credenciais reais sem pedido explícito.

## Atualização posterior

A criação de empresas aceita domínio próprio opcional (`custom_domain`) e preserva o subdomínio gerenciado (`subdomain.<TENANT_BASE_DOMAIN>`) como fallback. O DNS do domínio próprio continua sendo responsabilidade do provedor da empresa.

O acesso administrativo global é separado do acesso das empresas: administradores globais entram por `/platform/login`, enquanto usuários de tenant entram por `/login`. O painel possui aliases `/platform/dashboard`, `/platform/companies`, `/platform/subscriptions` e `/platform/audit`.

As configurações de cada assistência são controladas exclusivamente pelo super admin. No detalhe de uma empresa, o botão **Configurações** abre `/platform/companies/<organization_id>/settings`; essa tela edita a configuração da empresa selecionada, as opções de OS e os alertas/dashboard. Usuários do tenant, inclusive o dono com nível `admin`, são bloqueados em `/configuracoes`, `/configuracoes/site`, `/configurar` e `/emitente`.

Credenciais iniciais: `app/services/user_credentials.py` envia o e-mail de acesso com o endereço de login, o e-mail do usuário e a senha inicial/temporária. O super admin usa isso ao criar administrador, ao criar empresa e ao redefinir senha; o dono usa isso ao criar funcionário via `/api/usuarios`. Se o campo de senha ficar vazio, o backend gera a senha. A senha não deve ser registrada em `EventoLog`; SMTP precisa estar configurado para entrega real.

Áreas administrativas controladas pelo super admin: permissões, dados da empresa, site, mensagens administrativas, auditoria, privacidade e importação não aparecem no menu de usuários tenant e são bloqueadas também nas rotas/API por `platform_controlled_page_required` e `platform_controlled_api_required`. O usuário tenant ainda pode usar a área de usuários para cadastrar funcionários; isso é separado dessas configurações globais.

## Atualização posterior — 2026-11-05

### Vendas e navegação

- `/vendas/index` → **Nova venda** agora usa o formulário específico de vendas em `app/templates/pages/vendas_form.html`, com cliente/descrição, categoria, valor, vencimento/recebimento, status, forma de pagamento, parcelas, recorrência e comissão.
- O formulário genérico de transações financeiras continua em `/financeiro/adicionar`; o alias não deve renderizar o formulário de vendas.
- A correção foi feita em `app/routes/pages.py`: `vendas_adicionar_alias()` e `vendas_editar_alias()` renderizam `vendas_form.html`, enquanto `financeiro_adicionar_alias()` renderiza `zokyo_transacao_form.html`.
- A tela de vendas possui resumo lateral atualizado em tempo real e estilos compatíveis com o tema escuro.

### Senhas e criação de usuários

- A política central está em `app/utils/auth.py`: mínimo de 8 caracteres, uma letra maiúscula, uma minúscula, um número, um caractere especial e rejeição de senhas comuns.
- A política é aplicada no primeiro acesso do administrador da plataforma, cadastro de empresa, usuários, convites, redefinição/troca de senha, onboarding, provisionamento de tenant e criação de administrador pela plataforma.
- O cadastro de empresa exige confirmação da senha. O onboarding não persiste `owner_password`, `senha` ou `confirmar_senha` em `onboarding_data`.
- O componente `app/templates/partials/_password_requirements.html` exibe uma caixa visual interativa: cada requisito muda de estado enquanto o usuário digita e mostra a pontuação de requisitos atendidos. Ele é carregado por `app/static/js/password-policy.js` e estilizado em `app/static/css/components/forms.css`.
- Os campos de senha relevantes usam `data-password-input`; ao adicionar um novo formulário com senha, reutilizar esse atributo e o partial em vez de criar outra validação visual.

### Plataforma e planos

- A plataforma possui criação, edição e exclusão de planos em `app/admin/plans.py`, `app/routes/platform.py` e `app/templates/admin/partials/_plans.html`.
- A exclusão física é bloqueada quando o plano está vinculado a assinaturas/empresas. A interface mostra quantas empresas usam cada plano e orienta desativá-lo para impedir novas assinaturas.
- `platform.index` calcula `plan_subscription_counts` e o painel mostra total de planos e quantidade de planos ativos.

### Ícones, aparência e limpeza

- Emojis foram removidos da aplicação, do site de exemplo e das mensagens WhatsApp. A interface usa o sprite SVG existente ou SVG inline quando a página é independente.
- Foi adicionado o bloqueio visual de sublinhado azul nos itens do pipeline em `app/static/css/components/pipeline.css`.
- `app/static/css/unslop.css` continua carregado por último para consolidar o acabamento visual da aplicação.
- Após auditoria de referências, foram removidos somente os artefatos JSON históricos sem uso `producao_homologacao_etapa_16.json` e `relatorio_homologacao_etapa_15.json`. Migrações, testes, documentação, backups e arquivos operacionais não devem ser removidos sem confirmar suas referências.

### Validações recentes

- `python -m compileall -q app migrations`
- Compilação Jinja dos 97 templates existentes
- `node --check app/static/js/password-policy.js`
- `node --check app/static/js/validators.js`
- `git diff --check`
- `docker compose up -d --build app`; o serviço ficou saudável.

O detector visual usado na revisão não encontrou erro funcional; os avisos restantes são recomendações de design em páginas de autenticação independentes e não devem ser tratados como falha de execução.

## Atualização posterior — 2026-11-06 — Páginas de erro

- As páginas HTML de erro não usam `base.html`, sidebar, topbar ou menu da aplicação. O layout independente fica em `app/templates/errors/base.html` e é estilizado por `app/static/css/errors.css`.
- Existem páginas específicas para 400, 401, 403, 404, 405, 408, 500, 502, 503 e 504, com título, explicação e orientação de recuperação próprios. A página genérica `errors/error.html` continua atendendo códigos não mapeados.
- Os handlers globais agora cobrem 408, 502 e 504, além dos códigos já existentes. Respostas JSON de `/api/` continuam retornando JSON e não usam as páginas HTML.
- A interface de erro é responsiva, tem alternância de tema, foco visível, SVGs inline sem emojis, referência de suporte para erros 5xx e ações para tentar novamente ou acessar o sistema.

### Tela de criação de empresa

- `/platform?view=new-company` usa uma coluna única, com um formulário central de largura controlada e superfície única; não usar resumo lateral ou card auxiliar nessa tela sem nova validação visual.
- Os campos permanecem divididos em Dados da empresa, Responsável e Assinatura e acesso. O domínio/subdomínio e a hospedagem continuam com atualização dinâmica pelo `app/static/js/admin.js`.
- O acabamento usa as superfícies, bordas e tokens do admin em `app/static/css/components/admin.css`, com espaçamento reduzido no mobile.

### Sidebar do super admin

- O endpoint `platform.operations` precisava estar no conjunto de endpoints que ativa `platform_workspace`; sem isso, em alguns contextos o layout podia ser tratado como tenant e os links da sidebar ficavam inconsistentes.
- Os links **Operação e gargalos** e **Auditoria global** em `app/templates/admin/partials/_module_nav.html` agora têm estado ativo, `aria-current="page"` e o grupo usa o mesmo atributo de ação dos demais módulos.
- Correção adicional: o fallback de `admin_view` na navegação não pode ser `overview` quando a variável está ausente. Em `/platform/audit` e `/platform/operations`, usar string vazia para evitar marcar **Visão geral** indevidamente.

## Atualização posterior — 2026-11-06

### Hospedagem opcional de site por assinatura

- O painel `/platform?view=plans` permite definir, por plano, o percentual adicional cobrado pela hospedagem do site no servidor do Zokyo (`plans.hospedagem_percentual`). O percentual aceita de 0 a 1000; zero significa que a opção não acrescenta valor.
- Na criação de uma empresa e na tela de gerenciamento da empresa, o super admin pode marcar **Hospedar o site desta empresa no servidor do Zokyo**. A escolha é salva na assinatura (`organization_subscriptions.site_hospedado`), não no plano, porque empresas diferentes podem fazer escolhas diferentes usando o mesmo plano.
- O total mensal é calculado como preço base do plano mais o percentual de hospedagem. A função central é `Plan.preco_com_hospedagem()` e a assinatura expõe `preco_mensal_cobrado`; o checkout Asaas usa esse total ajustado.
- A tela mostra o percentual configurado e atualiza o resumo do preço imediatamente quando o plano ou a opção de hospedagem muda. A API `/platform/subscription` também retorna `site_hospedado` e `preco_mensal` já calculado.
- A migration correspondente é `20261106_0040_add_site_hosting_pricing.py`; aplicar com `flask --app wsgi:app db upgrade` antes de usar a funcionalidade.
- A tela de planos permite editar todos os campos do modelo, incluindo o ciclo de cobrança (`MONTHLY`, `QUARTERLY`, `SEMIANNUALLY` e `YEARLY`). O backend valida os ciclos antes de salvar e mantém compatibilidade com formulários antigos sem hospedagem/ciclo.

### Importação de dados externos — 2026-11-06

- `app/services/external_database_importer.py` mantém o importador Firebird legado e adiciona `GenericExternalImporter` para SQLite, MySQL, MariaDB, CSV, XLSX e ZIP com CSVs.
- A tela `/importacao/bancos` deixou de exibir fontes “em preparação”. Ela oferece perfil automático ou por entidade (clientes, produtos, ordens de serviço e financeiro), separador CSV, aba XLSX, conexão de rede e envio de arquivo pelo navegador.
- O adaptador usa aliases de colunas comuns (`clientes`, `customers`, `produtos`, `products`, `os`, `orders`, `lancamentos` etc.) e sempre preserva o fluxo de analisar schema, mapear, gerar prévia, revisar duplicidades e confirmar. Colunas sem alias são informadas como ignoradas.
- Uploads ficam temporariamente em `instance/import_uploads`; a senha da origem não vai para sessão, banco ou log. Os logs registram apenas tipo da origem, contagens, inválidos e duplicidades.
- A importação continua protegida por `platform_controlled_*`, portanto está disponível somente ao super admin conforme a regra de segurança já documentada. Sistemas proprietários sem exportação compatível devem ser exportados para CSV/XLSX e revisados no mapeamento antes da confirmação.
- Validações executadas nesta alteração: `python -m compileall -q app` e `node --check app/static/js/pages/importacao_bancos.js`. O host não possui `pytest` instalado.

### Sidebar de configurações — 2026-11-06

- Usuários vinculados a uma empresa, inclusive o dono/admin da assistência, não devem ver `Dados da empresa` nem `Meu Site` na sidebar.
- A condição anterior estava invertida e mostrava esses itens para tenants quando `can_manage_platform` era falso. A correção está em `app/templates/partials/_sidebar.html`, usando `current_user.organization_id` para ocultar os itens e também o módulo administrativo vazio.
- As rotas continuam protegidas por `configuration_page_required`; portanto esconder o link não é a única barreira de acesso.
- A rota do super admin `/platform/companies/<organization_id>/settings` também passa explicitamente `platform_workspace=True` e `current_platform_view="organizations"` ao template, evitando que a página seja renderizada como tenant quando aberta diretamente pela URL.
- Correção adicional: os endpoints `platform.company_settings`, `platform.company_settings_save`, `platform.company_settings_dashboard` e `platform.company_settings_os_options` foram incluídos em `GLOBAL_PLATFORM_ENDPOINTS`. Sem isso, o ABAC negava o acesso cross-tenant legítimo do super admin antes da rota executar.
- As páginas de erro usavam o endpoint inexistente `auth.login`; os links foram ajustados para `auth.login_page`, evitando que uma resposta 404/403 se transformasse em 500.

### Importação por empresa no painel global — 2026-11-06

- A importação não fica mais como módulo da assistência. O acesso principal está em `platform.company_settings_importacao`, em `/platform/companies/<organization_id>/settings/importacao`, dentro das configurações de cada empresa.
- `app/templates/pages/configuracoes.html` mostra o atalho **Importar dados** apenas no modo super admin. Donos e usuários tenant continuam sem esse link e sem acesso às APIs.
- O `organization_id` da empresa selecionada acompanha upload, teste, schema, mapeamento, prévia, logs e commit. A sessão compara esse destino novamente antes da gravação para evitar importação no tenant errado.
- `/importacao/bancos` virou compatibilidade: redireciona para a lista de empresas; com `organization_id`, encaminha para as configurações de importação da empresa.

### Auditoria LGPD — 2026-11-06

- O projeto foi classificado como cenário **C — híbrido**: base legada em produção/desenvolvimento contínuo e novas funcionalidades.
- O diagnóstico inicial está em `.lgpd/discovery.md` e o plano priorizado em `.lgpd/gaps.md`. O estado e o checkpoint estão em `.lgpd/STATUS.md`.
- A auditoria parou obrigatoriamente no checkpoint L1 antes do data mapping. Não implementar política jurídica, ROPA final, RIPD ou comunicação externa sem revisão/aprovação humana.
- Após o usuário pedir continuidade, foram concluídos os rascunhos técnicos L2–L8: `.lgpd/data-map.md`, `.lgpd/legal-basis.md`, `.lgpd/lia/`, `.lgpd/vendors/`, `.lgpd/transfers/`, `.lgpd/retention.md`, `.lgpd/anonymization.md`, `.lgpd/dsar/workflow.md` e `.lgpd/incidents/`. A política de privacidade L9 ainda não foi gerada por causa do checkpoint jurídico obrigatório.
- O usuário esclareceu o contexto: a Zokyo aluga o sistema para as assistências; cada assistência é, em regra, controladora dos dados de sua operação, enquanto a Zokyo é principalmente operadora e controladora independente apenas para os dados próprios do SaaS (contratação, cobrança, segurança, suporte e obrigações legais).
- A infraestrutura principal será um servidor local na residência do responsável, no Brasil. Isso reduz a hipótese de transferência internacional no servidor principal, mas não resolve automaticamente SMTP, Asaas, Meta, Cloudflare, S3, Sentry ou outros serviços externos eventualmente ativados.
- O sistema pode ser acessado por menores. Foi criado `.lgpd/eca-digital.md` com avaliação preventiva e plano para idade, responsável legal, controles parentais, antiperfilização e RIPD. A implementação ainda está pendente; não afirmar conformidade.
- As perguntas que ficaram pendentes foram explicadas assim: retenção significa por quanto tempo cada tipo de dado permanece guardado; provedores significa serviços externos usados além do servidor local. A política de privacidade L9 continua bloqueada até novo checkpoint explícito.
- Após o usuário escolher continuar no checkpoint, foi criado o rascunho `.lgpd/policies/privacy-policy-v1.0-draft.md` usando a skill de política de privacidade. Ele não foi publicado e não deve ser tratado como política vigente até preencher os campos pendentes e obter revisão jurídica explícita.
- A pedido de implementar o que faltava, foi criada a migration `20261106_0041_add_privacy_controls.py`: hash encadeado nos novos eventos de auditoria, campos de rastreabilidade para solicitações de titulares e tabela de incidentes.
- Foi implementado canal público `/privacidade/solicitacao` (também por slug de assistência), triagem super admin em `/privacidade/solicitacoes`, registro de incidentes em `/privacidade/incidentes` e o ROPA técnico `.lgpd/ROPA.md`.
- A migration foi aplicada no banco Docker com `docker compose exec -T app flask --app wsgi:app db upgrade` e o banco está em `20261106_0041 (head)`. O GET e POST do canal público foram testados com sucesso; o registro de teste foi removido. Os testes pytest não rodaram neste ambiente porque o módulo `pytest` não está instalado; `python -m compileall -q app migrations` passou.
- A governança configurável do super admin foi adicionada em `/privacidade/configuracao`, usando `PlatformSetting` para controlador, encarregado, canal, política e residência de dados. Não publica a política automaticamente.
- A auditoria ganhou `app/services/audit_integrity.py`, os comandos `flask --app wsgi:app audit-verify` e `audit-backfill --confirm`. A verificação encontrou e corrigiu a normalização de timezone, microssegundos e `organization_id`; o self-test retorna `hash_ok True`. O backfill foi executado no banco Docker e os 26 eventos históricos agora estão hash-encadeados; `audit-verify` retorna `checked=26`, `legacy=0`, `errors=[]`.
- Foi criado o RIPD técnico `.lgpd/RIPD/ripd-portal-laudos-menores.md` e o índice `.lgpd/RIPD/INDEX.md`, com metodologia de alto risco da Resolução CD/ANPD nº 2/2022, ISO 31000/ISO 27005, riscos, salvaguardas e decisão pendente. Ele não está aprovado.
- A exportação de titular em `app/services/privacy.py` agora inclui manifesto e arquivos disponíveis de fotos de laudos/OS, com validação de caminhos e hidratação pelo storage existente; arquivos ausentes continuam registrados no manifesto.
- A tela de retenção foi corrigida para o contexto multiempresa: o super admin seleciona a assistência, as políticas são consultadas/salvas com `organization_id` correto e nenhuma política é ativada sem aprovação explícita.
- O painel global de operações passou a exibir contadores agregados de solicitações LGPD abertas/vencidas e incidentes abertos/críticos, sem mostrar dados pessoais ou conteúdo dos pedidos.
- O workflow de incidentes agora permite ao super admin alterar status (aberto, investigando, contido ou encerrado), severidade, decisão de comunicação e ações corretivas em `POST /privacidade/incidentes/<id>`, com auditoria da atualização.
- A rota pública `/privacidade/politica` foi criada, mas permanece indisponível até o super admin preencher os dados institucionais e confirmar revisão jurídica em `/privacidade/configuracao`; o rascunho nunca é publicado automaticamente.
- Validação final desta etapa: `docker compose ps` mostra app, banco, Redis e servidor de site saudáveis; banco em `20261106_0041 (head)`; `audit-verify` conferiu 26/26 eventos, com `legacy=0` e `errors=[]`; `/privacidade/solicitacao` respondeu HTTP 200 e `/privacidade/politica` respondeu HTTP 503 enquanto não publicada. `compileall` e `git diff --check` passaram; pytest não está instalado neste ambiente.
- Correção posterior nos fluxos administrativos LGPD: formulários de solicitações/incidentes passaram a apontar para `POST /privacidade/solicitacoes/<id>` e `POST /privacidade/incidentes/<id>`. Pedidos concluídos exigem identidade validada e resposta; recusas exigem motivo; encerramento de incidente exige decisão de comunicação e ações corretivas. `python -m unittest discover -s tests -p test_privacy_workflows.py -v` verifica quatro cenários em SQLite, inclusive acesso negado ao administrador tenant.
- A migration `20261106_0042_incident_timeline.py` e o formulário de incidentes registram quando o controlador soube da afetação, quando comunicou ANPD/titulares e o protocolo. Horários exigem ISO 8601 com fuso e não podem estar no futuro nem preceder o conhecimento. A validação operacional de prazos úteis e a comunicação externa continuam manuais. A suíte `test_privacy_workflows.py` cobre também essa cronologia.
- Após o rebuild e `docker compose exec -T app flask --app wsgi:app db upgrade`, o banco local ficou em `20261106_0042 (head)`. O app retornou healthy; `audit-verify` manteve 26/26 eventos sem erros; o GET `/privacidade/solicitacao` retornou HTTP 200; os quatro testes de integração SQLite, `compileall` e `git diff --check` passaram.
- O formulário público de solicitações agora oferece explicitamente confirmação, bloqueio, informações sobre compartilhamento, consequências de não consentir, revogação de consentimento e revisão de decisão automatizada; os tipos são validados por um catálogo único em `app/services/privacy.py`. O texto da página deixa claro que o pedido é registrado no recebimento, sem deslocar o marco do prazo pela validação de identidade. O quinto teste cobre aceitação de tipos novos e rejeição de tipo desconhecido; atendimento imediato e execução de todos os direitos ainda dependem de fluxo operacional.
- Última validação local: rebuild do app concluído, Docker healthy, migração `20261106_0042 (head)`, auditoria `checked=26`, `legacy=0`, `errors=[]`, formulário público HTTP 200 com o novo catálogo, e cinco testes de integração SQLite aprovados.
- A avaliação ECA Digital foi refinada com inventário de seis fluxos: site de assistência, consulta pública de OS, portal de orçamento, API de cliente, pedidos de privacidade e painel interno. O acesso possível por menores justifica triagem, mas não prova automaticamente o enquadramento de cada fluxo. O Art. 9º, §1º, sobre verificação a cada acesso foi restringido corretamente a conteúdo/produto/serviço impróprio, inadequado ou proibido para menores; decisão sobre contas de menores e conteúdo 18+ dos sites depende do responsável pelo produto.
- A cadeia de auditoria agora usa a migration `20261106_0043_serial_audit_chain.py` para criar `audit_chain_head`, cuja linha é bloqueada transacionalmente por `SELECT ... FOR UPDATE` na criação de cada evento. Isso serializa a escrita entre workers e permite que `audit-verify` detecte exclusão da ponta da cadeia. A migração valida/backfilla eventos legados e se recusa a prosseguir se houver hash existente inconsistente. O sexto teste isolado verifica encadeamento e detecção de perda do último evento; UPDATE/DELETE físico e alerta agendado ainda faltam.
- `0043` foi aplicada com o app local parado e reiniciado em seguida: `db current` mostra `20261106_0043 (head)`, Docker healthy, `audit-verify` mostra `total=26`, `checked=26`, `legacy=0`, `errors=[]`, e o canal público respondeu HTTP 200. Os seis testes de integração SQLite, `compileall` e `git diff --check` passaram.
- A migration `20261106_0044_audit_append_only.py` instala triggers MariaDB/SQLite que bloqueiam UPDATE e DELETE diretos em `eventos_log`. Listeners ORM rejeitam a mesma mutação na aplicação; `audit-backfill` agora não altera cadeia selada e sinaliza evento legado inesperado para investigação. A suíte isolada cobre tentativa de update/delete ORM; usuários com privilégio DDL ainda conseguem remover triggers, por isso segregação de permissões e alertas permanecem necessários.
- `0044` foi aplicada no MariaDB local com o app parado: `db current` = `20261106_0044 (head)`, app healthy, `audit-verify` = `checked=26`, `legacy=0`, `errors=[]`; consulta a `information_schema.TRIGGERS` confirmou os triggers de bloqueio de UPDATE e DELETE.
- O processo dedicado de scheduler recebeu o job diário `verificar_auditoria`: a checagem completa sinaliza erro para o heartbeat/alerta operacional existente se encontrar hash inconsistente ou evento legado. O comando `audit-verify` também retorna falha em ambos os casos. Este job não está ativo no Docker local porque `SCHEDULER_ENABLED` é falso no serviço web e não há serviço de scheduler no compose; não habilitar no web sem isolar os outros jobs de notificação/retenção.
- O histórico de incidentes ganhou a migration `20261106_0045_incident_revisions.py`, tabela append-only com baseline de registros antigos e snapshot de cada criação/atualização nova, além de triggers MariaDB/SQLite contra UPDATE/DELETE. O super admin pode expandir o histórico de cada incidente. A migração foi aplicada no MariaDB local: `db current` = `0045 (head)`, app healthy, `audit-verify` = 26/26, legacy=0, errors=[]; `information_schema.TRIGGERS` confirmou quatro triggers (dois de eventos, dois de versões). Os sete testes de privacidade, `compileall` e `git diff --check` passaram.
- O scheduler dedicado também agenda `monitorar_prazos_privacidade` a cada 24h: pedidos de titulares vencidos ou a vencer em até 2 dias e incidentes com afetação conhecida há mais de 24h sem decisão de comunicação geram alertas estáveis sem PII. A listagem de pedidos destaca vencidos e permite filtrá-los pelo prazo mais antigo; Operação e gargalos mostra incidentes sem decisão. O job não roda no Docker de desenvolvimento enquanto não existir processo dedicado. Oito testes isolados passaram.
- A migration `20261106_0046_subject_request_history.py` acrescenta `response_channel`, `delivered_at`, `delivery_reference` e a tabela append-only `data_subject_request_revisions`, com baseline e triggers MariaDB/SQLite. Os eventos ORM gravam versões de toda criação/atualização; a atualização pelo super admin exige dados de entrega para estados finais, além de identidade para conclusão. O histórico aparece na listagem. Registros finais legados sem entrega permanecem identificáveis e exigem revisão; o sistema registra declaração/protocolo, sem comprovar recebimento externo. Oito testes do workflow e dois testes legados de privacidade passaram em SQLite isolado.
- `0046` foi aplicada no MariaDB local: `db current` = `20261106_0046 (head)`, app healthy, canal público HTTP 200, auditoria 26/26 sem erro e seis triggers confirmados. A base local tinha zero pedidos de titulares, portanto o backfill de baseline em base populada não foi observado em runtime. O teste legado só passa com `DATABASE_URL=sqlite:///:memory:` no processo de teste; o `.env` Windows aponta para MySQL local não exposto pelo Docker.
- `tests/test_subject_request_migration.py` exercita `0046` em SQLite descartável com um pedido antigo: confirma baseline, preservação da resposta e rejeição de UPDATE pelo trigger. Esse teste passou; não há pedido real na base MariaDB local para comparar o backfill nela.
- `docker-compose.prod.yml` passou a usar `APP_DB_USER`/`APP_DB_PASSWORD` para app/scheduler e `MYSQL_USER`/`MYSQL_PASSWORD` para migrate; serviço `db-access` com root executa `scripts/provision_runtime_db.py` após migrations, revoga privilégios antigos e concede apenas DML. O script valida identificadores, diferencia usuário runtime do migrador e verifica concessões finais. O Compose foi validado com variáveis fictícias; um usuário temporário no MariaDB local foi criado, leu os 26 eventos e foi removido. O Docker de desenvolvimento permanece com usuário único; a separação de produção ainda exige implantação real e proteção da conta root/host.
- `restore_database.py` ganhou guard: para restaurar exige `RESTORE_DATABASE_URL` para destino descartável ou `--confirm-in-place` para uso explícito de `DATABASE_URL`/mesmo nome de banco; `BrokenPipeError` agora revela stderr do cliente. `tests/test_restore_guard.py` tem dois testes. Um backup real do MariaDB local foi criado e restaurado em `zokyo_lgpd_restore_check` com URL de destino explícita; auditoria no banco restaurado = 26/26, legacy=0, errors=[], seis triggers presentes. O teste inicial falhou por `URL.__str__` mascarar a senha, corrigido no comando de teste com `render_as_string(hide_password=False)`; fonte não foi tocada. Banco de teste e dump temporário foram removidos. Backup externo e restore com dados de produção ainda não comprovados; o dump atual é inicialmente plaintext e exige criptografia/cópia operacional.
- `scripts/backup_secure.py` agora gera dump em `TemporaryDirectory` privado, cifra com `BACKUP_ENCRYPTION_KEY`, verifica decriptando/checando SHA-256 e publica apenas `.sql.gz.enc` com `.enc.json`. `restore_database.py` decripta `.enc` em temporário privado e confirma hashes antes do restore. `tests/test_secure_backup.py` valida ida/volta e detecção de alteração. Teste real no MariaDB local: backup cifrado criado, `--verify-only` passou, CLI restaurou em `zokyo_lgpd_encrypted_check`, auditoria 26/26 e seis triggers; banco, arquivos e chave de teste removidos. Produção ainda precisa de agendamento, cópia externa, retenção e restore periódico comprovado. O comando legado `backup_database.py` continua gerando plaintext e deve ficar restrito a diagnóstico/compatibilidade.
- `docker-compose.prod.yml` tem serviço `backup` opcional em profile `maintenance`, com conta de migração e volume `backups_data`; o Dockerfile cria `/app/backups` com dono `zokyo`. `docker compose ... --profile maintenance config --format json` com variáveis fictícias confirmou a separação app/runtime e backup/migration, perfil e volume. O serviço não agenda por si; agendamento/cópia offsite e backup cifrado dos uploads ainda faltam. `backup_secure.py` e `restore_database.py` aceitam `BACKUP_ENCRYPTION_KEY` via `--env-file` para uso local.
- `scripts/secure_storage.py` cria e restaura backups cifrados dos uploads locais; o `backup-storage` do Compose de produção monta `uploads_data` somente leitura e publica os artefatos no volume `backups_data`. Restore confere SHA-256, AES-GCM, manifesto e conteúdo antes da extração, e protege uploads ativos/destinos não vazios. S3, offsite, agendamento e evidência de produção continuam pendentes.
- `backup_offsite.py` aceita `--require-kind database-backup --require-kind private-storage-backup` para exigir os dois pares recentes/íntegros antes do rclone; filtro de cópia só inclui `.enc` e `.enc.json`. `docs/DISASTER_RECOVERY.md` foi atualizado para os comandos cifrados. Nenhum remoto/agenda real foi configurado.
- A área temporária em claro do backup de banco e de uploads foi movida para o diretório temporário do contêiner; o volume persistente de backups recebe somente arquivo cifrado/metadata. Testes de ida e volta, adulteração, destino ativo, manifesto extra e par offsite passaram. O volume local de uploads estava vazio no ensaio Docker; o teste de arquivos reais foi em diretório descartável. A imagem foi reconstruída e a configuração de produção validada; nenhum restore de produção foi realizado.
- No Compose de produção, `BACKUP_ENCRYPTION_KEY` está apenas em `backup` e `backup-storage`, fora de `app`, `scheduler` e `migrate`; `docs/DEPLOY.md` explica a injeção temporária da chave para `production-check --strict-integrations`. A configuração expandida confirmou essa segregação. Proteção do disco temporário e das chaves reais ainda depende da infraestrutura.
- Importações externas: `app/utils/import_files.py` limita a limpeza ao diretório e ao padrão UUID do endpoint. Arquivo temporário é apagado após commit bem-sucedido; abandonados há mais de 24 horas são limpos no próximo upload e pelo job diário `limpar_importacoes_temporarias` do scheduler dedicado. O prazo é operacional para upload temporário, não política aprovada de dados definitivos. Teste isolado de limpeza passou.
- Rebuild local após a limpeza de importações: app Docker healthy, `audit-verify` 26/26 (`legacy=0`, `errors=[]`), `compileall` passou. Scheduler de desenvolvimento permanece desligado, então observar o primeiro ciclo real do job em produção.
- `app/routes/platform.py` registra leitura bem-sucedida de páginas do super admin (`platform_access`, tipo `acesso`) com usuário e escopo/empresa, sem query string. `app/templates/pages/logs.html` permite filtrar o novo tipo. Teste isolado em `tests/test_privacy_workflows.py` confirmou duas leituras, cadeia íntegra e ausência de evento para tenant negado. Revisão periódica/motivo individual de suporte ainda são pendências LGPD-18.
- Rebuild local do registro de acessos: app Docker healthy, `audit-verify` 27/27 (`legacy=0`, `errors=[]`), nove testes de workflow de privacidade passaram.
- A ação antiga de "anonimizar cliente" só removia campos da tabela `clientes`, mas logs e outros dados permaneciam. Agora a UI a chama de "Remover dados cadastrais", o serviço bloqueia também coletas vinculadas, não gera solicitação de titular `completed` sem entrega, e a mensagem avisa sobre histórico/auditoria/backups. Três cenários do teste `tests/test_privacy.py` passaram por execução direta; anonimização integral continua pendente.
- As operações novas de auditoria de cliente, usuário, coleta, cobrança e incidente foram alteradas para registrar IDs sem repetir nome/e-mail/título; eventos antigos permanecem imutáveis. É necessário revisar outros logs livres, inclusive `usuario_nome` desnormalizado, antes de afirmar minimização completa.
- Após essas mudanças, três cenários diretos de privacidade e nove testes de workflow passaram, `compileall` passou, app Docker healthy e auditoria 27/27 sem erro. Ainda não há homologação dos fluxos de cliente/cobrança em produção.
- `app/utils/field_crypto.py` não devolve mais `None` quando a chave/salt está errado; lança `FieldDecryptionError` para impedir sobrescrita silenciosa. Teste de falha com salt errado/recuperação com salt correto passou. `docs/KEY_MANAGEMENT.md` descreve chaves, custódia e recuperação; rotação segura de campos/índices e cofre real ainda faltam.
- Em `FLASK_ENV=production`, `field_crypto` e `blind_index` recusam respectivamente `ENCRYPTION_SALT` legado e chave de índice implícita; dois testes novos e dois existentes passaram. O fallback continua disponível somente em desenvolvimento/legado para leitura controlada.
- Rebuild local da imagem após a mudança de chaves: app Docker healthy e auditoria 27/27 sem erros. Produção real não foi validada.
- Configurações da empresa no painel global ganharam “Privacidade dos clientes”, com lista/busca, ficha, exportação e remoção cadastral por `organization_id` + `client_id`, sempre super admin. Os links antigos das páginas de cliente tenant foram retirados. `can_manage_platform` agora exige `organization_id=None`, inclusive quando o e-mail consta em `PLATFORM_ADMIN_EMAILS`. Exportação administrativa é auditada sem registrar DSAR `completed`; concessão manual de consentimento não é oferecida na nova tela por falta de evidência de coleta. Dez testes de workflow passaram, incluindo duas empresas e tenant negado.
- Rebuild local dessa integração: app Docker healthy, auditoria 27/27 sem erro, `compileall`, três testes diretos de privacidade e dez testes de workflow aprovados. Produção real ainda não foi homologada.
- Migration `20261106_0047_subject_identity_evidence.py` acrescenta método, protocolo e horário da conferência de identidade de pedidos de titulares; o formulário exige método/protocolo ao marcar a validação e o histórico append-only preserva os valores. Dados legados ficam nulos. Testes de workflow e migração SQLite passaram; `db current` no MariaDB local = `0047 (head)`, app Docker healthy, `audit-verify` 27/27. Não há verificação externa automática da identidade.
- Contexto confirmado pelo usuário: Zokyo é **um projeto de teste para avaliar se vale continuar a ideia**, sem razão social/CNPJ/endereço/canal institucional/encarregado definidos. Não inventar esses dados nem publicar política jurídica como vigente. A infraestrutura local no Brasil é plano futuro; fluxos de menores e conteúdo 18+ ainda não foram esclarecidos. Continuar controles técnicos no protótipo e manter pendências institucionais explícitas.
- Migration `20261106_0048_consent_evidence.py`: consentimentos agora têm versão do aviso e referência da evidência; triggers MariaDB/SQLite bloqueiam UPDATE/DELETE. Concessão manual foi removida da ficha, e o serviço exige origem de coleta direta e metadados para concessão. Registros antigos ficam com evidência desconhecida. No MariaDB local: `0048 (head)`, triggers confirmados, app healthy, auditoria 27/27. Ainda faltam formulário de coleta real, aviso aprovado/publicado e checagem do consentimento nos tratamentos opcionais; ver `.lgpd/consent.md`.
- `/privacidade/politica` não gera mais uma política genérica com afirmações não verificadas. Ela só redireciona para a URL HTTPS de um documento aprovado, mediante dados institucionais e confirmação de revisão na configuração. Sem documento configurado, retorna 503. Teste de workflow cobre ausência, URL inválida e configuração válida; o protótipo permanece sem política vigente.
- Exportação de cliente em `/platform/companies/<id>/settings/privacy/clients/<id>/export` agora exige POST, CSRF e motivo controlado, registrado no evento de auditoria sem texto livre. O formulário na ficha permite escolher pedido do titular, suporte solicitado ou investigação de incidente. O motivo ainda é autodeclarado; não há vínculo automático com ticket/protocolo. Teste integrado cobre motivo inválido/ausente, isolamento entre empresas e ZIP válido.
- Remoção cadastral na mesma ficha também exige motivo controlado no POST (pedido do titular, cadastro duplicado ou minimização aprovada). Sem motivo, responde 400 antes da mutação; o evento registra o código. Teste confirmou que o cadastro permanece intacto quando a justificativa falta.
- A triagem de DSAR ganhou associação manual de empresa e cliente após identidade validada com método/protocolo. O servidor verifica o par, impede troca de vínculo já gravado e inclui IDs nas novas revisões append-only. Na ficha do cliente, exportação por pedido do titular exige esse vínculo e auditoria com ID do pedido; remoção exige pedido em andamento de eliminação/anonimização; investigação exige incidente da empresa. Pedidos de outra empresa e incidentes de outra empresa são rejeitados. A verificação da identidade ainda é declaração do operador; suporte/duplicidade/minimização não têm comprovante externo automático.
- Migration `20261106_0049_encrypt_privacy_fields.py`: novos pedidos de titulares e incidentes cifram identificadores, descrições, notas e snapshots via `EncryptedText`; colunas curtas viraram `TEXT` e o índice de e-mail em claro dos pedidos foi removido. O MariaDB local tinha zero pedidos/incidentes antes da migration; `0049 (head)`, app healthy, auditoria 27/27. Teste de fluxo confere ciphertext no SQL bruto e leitura ORM; teste SQLite confirma que legado permanece legível. A migration não recriptografa dados antigos nem backups; downgrade bloqueado para evitar truncamento. Ver `docs/KEY_MANAGEMENT.md`.
- Novo comando `flask --app wsgi:app privacy-encryption-audit --strict` conta, sem imprimir PII, campos de pedidos/incidentes e revisões ainda sem prefixo de criptografia. Reprova valor legado ou banco/schema indisponível. No MariaDB local após rebuild: zero valores, app healthy, `0049 (head)`, auditoria 27/27. Teste isolado cobre detecção, saída sem PII, resultado limpo e falha fechada. O comando não lê backups; está no checklist de go-live.
- `privacy-encryption-audit` agora também autentica/decripta cada ciphertext das colunas cobertas com a chave atual; token ilegível reprova até sem `--strict`. Prefixo com maiúsculas diferentes conta como legado em claro, evitando falso zero com `LIKE` case-insensitive. Teste isolado cobre corrupção, prefixo falso e saída sem PII. MariaDB local após rebuild: zero legados e zero ciphertexts ilegíveis, app healthy, auditoria 27/27. Continua sem ler backups ou colunas não inventariadas.
- Exportação administrativa do cliente passou a incluir e-mail, coletas, solicitações vinculadas e mais campos técnicos dos laudos. Consultas de todas as entidades do ZIP agora filtram empresa explicitamente. OS e transações usam whitelists para excluir custos internos, comissões, dados de técnico e payloads do gateway. O ZIP orienta revisão de texto/imagens e não conclui DSAR. Novo `tests/test_subject_export.py` cobriu dados de duas empresas, inclusive vínculos inconsistentes, e confirmou isolamento/cobertura. Ainda faltam portabilidade homologada e revisão humana de conteúdo livre antes da entrega.
- Cada ZIP de exportação administrativa agora recebe SHA-256 dos bytes finais, registrado no evento append-only e no cabeçalho `X-Export-SHA256`. Testes de workflow e exportação compararam digest do corpo, cabeçalho e evento. Isso permite conferir artefato preservado, mas não prova envio ou recebimento pelo titular; ver `.lgpd/dsar/workflow.md`.
- `20261107_0050_subject_export_evidence.py` acrescenta SHA-256 e horário do último ZIP preparado ao pedido de titular vinculado. A rota de exportação grava ambos na mesma transação do evento auditado e a revisão append-only; a listagem exibe o hash. Não altera o status nem registra entrega. Pedidos antigos mantêm os campos vazios, e o arquivo não fica guardado no servidor. O usuário confirmou que Zokyo é somente protótipo nesta fase: manter dados institucionais e aprovação jurídica pendentes, sem pedir CNPJ/encarregado como bloqueio para continuar controles técnicos.
- Após `0050`, Docker app healthy, `db current` = `0050 (head)`, `db check` sem mudanças, auditoria 27/27 íntegra, inspeção de criptografia sem claro/ilegível. Doze testes de workflow e teste de migration passaram. Pendem evidência externa de entrega, homologação de portabilidade e revisão operacional de dados de terceiros antes de entregar exportações reais.
- A área global de privacidade por cliente passou a exigir campo `protocol` para exportação por suporte e remoção cadastral por duplicidade/minimização. Só aceita 4–40 caracteres ASCII em maiúsculas/números/hífens, registra `protocolo=<código>` no evento e recusa ausência/formato inválido com HTTP 400. Não verifica se o atendimento externo existe; a validação ainda é operacional. Testes de workflow cobrem os três casos.
- `20261107_0051_notification_redaction.py` adiciona `Notification.redacted_at`. A política aprovada de retenção da categoria `notifications` passa a limpar somente mensagens enviadas antigas, removendo destinatário, payload, `os_id` e erro, mas conservando ID/chave de idempotência/horários para evitar reenvio acidental. Falhas e envios manuais pendentes ficam para tratamento. A limpeza registra evento agregado sem PII. Dois testes de retenção e o teste isolado da migration passaram; `.lgpd/retention.md` descreve limites.
- `0051` aplicada no MariaDB local: app healthy, `db current` = `0051 (head)`, `db check` sem diff, auditoria 27/27 e inspeção de criptografia sem claros/ilegíveis. A política não foi ativada. Testes: 3 de retenção/migration, 12 de notificações e 7 de contratos de serviços/modelos.
- O job `verificar_auditoria` passou a chamar `assert_event_chain(record_success=True)` e registrar evento imutável com quantidade conferida, último ID e hash da ponta anterior somente após verificação íntegra. `audit-verify` expõe esses dois valores no JSON. `app/admin/operations.py` agora calcula atraso de heartbeat conforme frequência real de cada tarefa e sinaliza ausência de verificação da auditoria; antes todos os jobs eram considerados atrasados após 1 h. Testes: 6 operacionais e 13 de workflow. A prova permanece interna até configurar cópia externa independente.
- Rebuild local após a mudança de auditoria: app healthy, banco `0051 (head)`, `audit-verify` 27/27 íntegro com hash da ponta no JSON, auditoria de criptografia sem valores em claro/ilegíveis, diff sem whitespace inválido. Scheduler local segue desligado; o registro automático foi exercitado apenas em teste isolado.
- O fluxo de auditoria pode gerar `*.audit-anchor.json` sem PII em `AUDIT_ANCHOR_DIR` após verificação íntegra e conferir a âncora anterior contra a cadeia atual. `docker-compose.prod.yml` monta `backups_data` no scheduler e define `/app/backups` como diretório de âncoras; `backup_offsite.py` inclui o padrão e aceita `--require-audit-anchor`. `audit-verify --anchor-dir` compara manualmente. Testes de operação/backup cobrem escrita, divergência e ausência de âncora. Sem remoto externo configurado no protótipo, não declarar âncora externa operante.
- Validação dessa etapa: 30 testes combinados passaram; o restaurador de uploads agora relata arquivo do manifesto ausente com erro específico (um teste existente estava falhando). Compose de produção passou `config --quiet` com variáveis falsas de validação, sem configurar produção. Docker local healthy, `0051 (head)`, verificação de auditoria 27/27 com `--anchor-dir` vazio e criptografia zero/zero. Nenhuma cópia remota nem scheduler foram ativados.
- `20261107_0052_encrypt_notifications.py` amplia `notifications.recipient` e converte `payload` JSON para texto cifrado, cifra `last_error` e migra linhas legadas usando chave/salt atuais. `EncryptedJSON` mantém `dict` no ORM e falha fechado em ciphertext/JSON inválido. `privacy-encryption-audit --strict` inclui as três colunas. Testes dedicados verificaram SQL bruto sem PII, leitura, corrupção e legado; testes de notificações/OS/retenção passaram. Aplicação no MariaDB local ainda pendente nesta etapa.
- `0052` aplicada no MariaDB local: app healthy, `db current` = `0052 (head)`, `db check` sem mudanças, scanner de criptografia zero/zero, auditoria 27/27. Teste de inserção no MariaDB confirmou ciphertext em `recipient` e `payload`, com rollback. A base local tinha zero notificações antes da migração; o backfill de linhas legadas só foi exercitado em SQLite. Backups antigos ainda podem conter notificações em claro.
- Suíte completa Python após `0052`: 341 passaram, 1 ignorado, 34 falharam. O teste de migration esperava a revision antiga `0038`; foi atualizado para `0052` e passou isoladamente. As demais falhas observadas concentram-se em expectativas de permissões/rotas/landing anteriores; não declarar suíte completa verde nem atribuir todas as falhas à criptografia. Testes focados de notificação, OS, retenção, scanner e migração passaram.
- O canal público de DSAR ganhou limite adicional configurável `PRIVACY_REQUEST_LIMIT_PER_HOUR` (padrão 10 POSTs/hora por IP), compartilhado entre `/privacidade/solicitacao` e `/privacidade/solicitacao/<slug>`. Resposta 429 tem `Retry-After`, não grava pedido nem repete e-mail; formulário, erro e confirmação usam `Cache-Control: no-store, private`. Texto livre orienta minimização. O bucket dedicado usa HMAC do IP com finalidade separada; os limites globais/API também gravam pseudônimos HMAC de 43 caracteres (inclusive no fallback MariaDB). Vinte e dois testes de workflow/rate limit passaram; 10 testes de autenticação passaram e um teste de configurações preexistente continuou falhando com 302 esperado como 200. Após o primeiro rebuild Docker, GET retornou 200 sem cache, DB `0052 (head)`, auditoria 27/27 e scanner de criptografia zero/zero.
- Migration `20261107_0053_clear_legacy_rate_keys.py` apaga contadores temporários de `api_rate_limits` anteriores, que poderiam guardar IP em claro; isso reinicia uma vez os limites globais/API no deploy. Bloqueios de login são preservados. Vinte e nove testes focados de workflow/rate limit/migrations passaram. Após rebuild, app Docker healthy, `db current` = `0053 (head)`, `db check` sem operações pendentes, auditoria 27/27 íntegra e scanner de criptografia zero legados/ilegíveis.
- Migration `20261107_0054_pseudonymize_login_attempts.py` converte chaves antigas de login para pseudônimos HMAC, mantendo tentativas e bloqueios ativos; runtime usa mesma derivação. O banco local tinha 1 registro e depois do upgrade ficou com 0 IPs em claro em `login_attempts`; 23 testes focados de rate limit/autenticação/migração passaram. Ainda verificar logs HTTP/proxy e backups anteriores; HMAC não é anonimização. A limpeza de registros vencidos depende do scheduler, não está garantida no protótipo local.
- Validação combinada de DSAR público, rate limit, autenticação e migrations: 39 testes aprovados. Docker app healthy, banco `0054 (head)`, `db check` sem alterações, auditoria 27/27 íntegra e scanner de criptografia zero/zero. A suíte geral continua com falhas anteriores; não afirmar validação total do sistema.
- Logs de acesso novos: Gunicorn e Nginx registram somente horário, método, status, tamanho e duração, sem IP, URL, query, referer ou user agent. O filtro/formatador Flask mascara também tracebacks e argumentos de log em dicionário. Teste real detectou inicialmente que Nginx escrevia dois logs (um herdado com URL completa); após pôr `access_log` no `server`, requisição com marcador na query retornou 200 e só gerou uma linha mínima, sem marcador/IP. Gunicorn também retornou 200 sem marcador/IP nos logs. `nginx -t`, `gunicorn --check-config` e 22 testes focados passaram. Logs históricos/erro do proxy, Docker/journald, serviços externos e backups continuam pendentes de revisão e retenção operacional.
- O logger Flask agora não propaga para root e preserva o handler rotativo; `app.*` herda o handler, Werkzeug/SQLAlchemy usam handlers filtrados. Teste de arquivo confirmou `[EMAIL]` sem endereço original. Após rebuild da correção, app Docker healthy e 22 testes focados aprovados.
- Migration `20261107_0055_encrypt_session_signature_metadata.py`: `UserSession.ip_address/user_agent` e `OrderSignature.signer_name/ip_address` usam `EncryptedText`; scanner de criptografia inclui as quatro colunas. No MariaDB local havia 17 sessões e zero assinaturas; upgrade `0055 (head)`/`db check`/scanner zero claro e zero ilegível/app healthy. Backfill de assinaturas testado em SQLite, não em MariaDB com dados reais. Teste da tela de sessões confirma IP legível no HTML enquanto o banco guarda ciphertext. Backups anteriores à migration permanecem fora da inspeção. Oito testes de migration/novos, 18 de auth/assinatura/scanner/modelos e 17 após reforçar teste da tela passaram.
- `app/services/retention.py` agora oferece `user_sessions` como categoria de política por assistência, desativada por padrão e dependente de aprovação explícita. O job elimina somente sessões expiradas ou revogadas há mais tempo que o prazo aprovado, preserva sessões ativas e de outras empresas e grava evento agregado. O painel mostra a categoria; teste de rota rejeitou ativação sem aprovação. 19 testes de retenção/workflow passaram. Sessões de super admin (`organization_id=NULL`) e prazo final ainda pendem; scheduler local desligado.
