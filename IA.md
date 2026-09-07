# Memória técnica do Zokyo para IAs

Este é o documento de continuidade do projeto. Toda IA que trabalhar neste repositório deve lê-lo antes de alterar código, banco, infraestrutura ou documentação. Ele não substitui os documentos especializados em `docs/`; serve como mapa, histórico curto e conjunto de invariantes para evitar retrabalho e regressões.

Última atualização: 2026-09-03.

## Objetivo do produto

O Zokyo é uma plataforma multiempresa para assistências técnicas. Centraliza clientes, ordens de serviço, bancada, estoque, financeiro, laudos, coleta/entrega, portal do cliente, relatórios, comunicação e operação SaaS.

O objetivo atual não é acumular módulos. A prioridade é transformar a implementação existente em um produto simples, confiável e seguro para uso diário, primeiro em piloto controlado e depois em produção comercial.

## Estado resumido

- Aplicação Flask e site público executam em Docker com MariaDB.
- Schema gerenciado por Alembic até a migration `20260731_0012`.
- 215 testes Python aprovados na última auditoria completa.
- 200 cenários Playwright executados em compact, mobile, tablet, desktop e wide.
- Auditoria visual cobre overflow, runtime, HTTP 500 e violações WCAG sérias.
- Teste local de 150 requisições simultâneas passou após correção do rate limit persistente.
- Ruff, compilação Python, validação JavaScript e auditorias de dependências passaram.
- O código está apto para piloto controlado, mas o ambiente comercial ainda não foi homologado.
- Serviços Docker foram desligados preservando os volumes ao final da última sessão.

Consulte [oque_falta.md](oque_falta.md) para o checklist atual e [CHANGELOG.md](CHANGELOG.md) para a evolução versionada.

## Tecnologias

### Backend

- Python 3.11 como versão de referência em Docker e CI.
- Flask 3, Flask-SQLAlchemy e SQLAlchemy 2.
- Flask-Migrate/Alembic para schema.
- MariaDB 11 em desenvolvimento integrado e produção.
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
- Logs de auditoria, métricas, healthchecks, alertas e retenção LGPD.
- Importação de bancos externos, incluindo legado Firebird.

## Regras que não podem ser quebradas

1. Nunca usar `db.create_all()` em instalação ou produção. O schema real evolui somente por Alembic.
2. Toda consulta e mutação de dado empresarial deve respeitar `organization_id` e o tenant da sessão.
3. Perfis sem permissão não podem obter dados sensíveis nem por API nem por página HTML.
4. Técnico não recebe acesso financeiro sensível por padrão; atendente não altera configuração crítica.
5. OS não pode ser finalizada/entregue sem pagamento integral conforme a regra atual.
   A edição da OS também deve bloquear a entrega; nunca criar recebimento implícito apenas pela mudança de status.
6. Arquivamento deve preservar histórico; não transformar exclusão lógica em remoção destrutiva acidental.
7. Produto ou serviço inativo não pode entrar em nova OS.
8. Movimentação de peça usada na OS deve manter estoque e histórico consistentes.
9. Observação interna não pode vazar para o portal do cliente.
10. PDFs, uploads, fotos, assinaturas e laudos privados exigem autorização e isolamento do tenant.
11. Tokens, documentos, e-mails e segredos não devem aparecer integralmente em logs.
12. A assinatura atual é simples e não deve ser apresentada como certificação ICP-Brasil.
13. Rate limits persistentes precisam continuar seguros com múltiplos workers. No MariaDB, o contador global usa upsert atômico e retry limitado para erros transitórios 1020, 1205 e 1213.
14. O scheduler deve rodar em processo dedicado, nunca duplicado em cada worker Gunicorn.
15. Segredos reais, bancos, uploads, dumps e arquivos `.env` não entram no Git.

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

Em 2026-09-03, o CI falhava antes de testar o produto por dois erros de infraestrutura: importação do script concorrente fora da raiz e tag inexistente do Trivy. O workflow executa o script como módulo e fixa `trivy-action` por SHA. Ao atualizar Actions, confirmar a referência publicada e preferir SHA imutável para ferramentas de segurança.

O scan seguinte expôs vulnerabilidades HIGH nas bibliotecas vendorizadas das ferramentas de build da imagem base. O `Dockerfile` atualiza essas ferramentas, instala o lock e remove `pip`, `setuptools` e `wheel` da imagem final, pois não são necessários em runtime. Não reduzir a severidade nem ignorar CVEs apenas para deixar o workflow verde; remover ou atualizar a camada vulnerável e confirmar no Trivy.

O CI Python precisa instalar `requirements-prod.lock` e `requirements-dev.txt`: a suíte usa ferramentas de desenvolvimento, enquanto o smoke de carga valida o servidor Gunicorn real. A etapa confirma `/healthz` antes de iniciar carga e deve falhar cedo se o processo não subir.

O `gunicorn.conf.py` aceita `GUNICORN_ACCESSLOG`, `GUNICORN_ERRORLOG` e `GUNICORN_PIDFILE`. A imagem usa diretórios persistentes preparados pelo Dockerfile; o CI usa stdout/stderr e `/tmp`.

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
