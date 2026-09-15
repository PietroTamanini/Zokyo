# Changelog

## Unreleased

### Corrigido

- CRUD financeiro da API agora registra `EventoLog` em criação, edição e exclusão, com tenant correto e sem copiar a descrição livre da transação para a auditoria.
- Fluxos centrais da API de OS agora registram `EventoLog` em criação, edição, exclusão, vínculo/remoção de peças e reservas, sem copiar defeitos ou observações livres.
- API de estoque agora registra eventos gerais de edição, exclusão direta, ajuste e recebimento de lote, mantendo justificativas livres na trilha especializada de movimentações.
- Privacidade e relatórios salvos ganharam cobertura de auditoria geral: consentimento, exportação, anonimização, criação e exclusão de relatório agora são validados sem copiar dados pessoais, nomes livres ou destinatários.
- Planos, assinaturas, checkout/cancelamento Asaas e webhooks de billing agora possuem eventos administrativos resumidos, sem payloads, documentos, tokens ou identificadores externos sensíveis.
- Recuperação/reset de senha, aceite de convite, troca de senha pela API e regeneração de token agora têm auditoria segura em `EventoLog`, sem registrar e-mail, token ou senha.
- Portal público agora registra evento de segurança para decisão negada com token válido, sem gravar o token ou dados internos da OS.
- Corrigida a regressao do CI no benchmark, mantendo o lint estrito sem ignorar o arquivo inteiro.
- Corrigida a agregacao de ordens atrasadas que causava erro 500 no dashboard.
- A contagem de pecas pendentes do dashboard agora filtra explicitamente a organizacao no SQL manual.
- Mutacoes ORM de objetos pertencentes a outro tenant agora sao bloqueadas antes do flush.
- O contador sequencial de laudos passou a integrar o escopo central e ganhou chave estrangeira para a organizacao.
- O teste concorrente de numeracao agora provisiona seu tenant, respeitando a nova integridade referencial.
- O pool MariaDB agora usa LIFO, `READ COMMITTED` e limites configuraveis por ambiente.
- Corrigido o CI: o teste concorrente de laudos agora carrega o projeto pela raiz e o scanner Trivy usa uma versão existente fixada por SHA imutável.
- Atualizadas e fixadas as ferramentas de build da imagem para remover vulnerabilidades HIGH presentes nas cópias vendorizadas do `setuptools` da imagem base.
- Removidos `pip`, `setuptools` e `wheel` da imagem final após instalar as dependências; essas ferramentas não são necessárias em runtime e mantinham cópias vendorizadas vulneráveis.
- O job Python agora instala o lock de produção antes das ferramentas de teste e inicia Gunicorn como módulo, com verificação explícita de saúde antes do teste de carga.
- Logs e pidfile do Gunicorn agora são configuráveis no smoke de CI, evitando dependência dos diretórios persistentes existentes apenas na imagem de produção.
- Eliminada falha de concorrência do rate limit global no MariaDB, com incremento atômico e retry limitado para conflitos transitórios reconhecidos.
- Tornada determinística a auditoria E2E do modal de clientes quando a tela vazia oferece mais de um link com o mesmo texto.
- Corrigida a comparação entre vencimentos sem fuso do banco e horário UTC na inadimplência por OS, evitando erro 500 com cobrança vencida.
- O resumo financeiro agora é identificado como resumo do período e acompanha corretamente filtros semanais, anuais e personalizados.
- Comissões no lucro por OS agora consideram somente receitas pagas, sem incorporar comissão indevida de uma despesa vinculada.
- Fechado o atalho do formulário de edição que permitia entregar uma OS com saldo aberto criando uma quitação implícita; todas as rotas agora exigem pagamento previamente registrado.
- Eventos de OS do painel, API, coleta, orçamento, cobrança e garantia agora entram na fila persistente usando templates e chaves idempotentes.
- Templates disparados pelo portal público agora são resolvidos pelo tenant explícito da OS, impedindo uso de mensagem ou configuração de outra empresa.
- Mudanças de status feitas no formulário de edição agora registram histórico, notificam o cliente e preservam a devolução de estoque no cancelamento.
- Corrigida a atribuição de tenant em `EventoLog`: mutações autenticadas agora usam a organização da requisição em vez do fallback fixo para a empresa 1.

### Verificado

- 223 testes Python, lint, compilação e validação JavaScript aprovados em 2026-09-15.
- Indicadores de pagamento incompleto, custo de peças, custo de mão de obra, comissão, lucro e inadimplência por OS cobertos por testes dedicados.
- Auditoria autenticada das telas em compact, mobile, tablet, desktop e wide, incluindo runtime, HTTP 500, overflow e WCAG.
- Teste local com 150 requisições simultâneas sem erro após a correção de concorrência.

### Documentação

- Adicionado `IA.md` como memória técnica viva para continuidade entre agentes e desenvolvedores.
- Adicionada matriz formal de auditoria das mutações, com mecanismos atuais e lacunas priorizadas por domínio.
- Reescrita a lista de conclusão do produto para separar código, infraestrutura, homologação e decisões externas.
- Adicionados checklist de go-live e política de suporte/operação.

- Revisao geral removeu entrypoints, templates, assets e utilitarios sem uso comprovado.
- PDFs de OS foram consolidados em ReportLab, com escape de conteudo; `pdfkit`/wkhtmltopdf foram removidos.
- Cryptography e Pillow foram atualizados para versoes sem vulnerabilidades conhecidas; `pip-audit` passou sem achados.
- Arquivamento de clientes e fornecedores passou a preservar OS, laudos, pecas, financeiro e auditoria.
- APIs agora rejeitam chaves estrangeiras de outro tenant e perfis somente consulta nao executam mutacoes.
- Ruff foi ampliado para imports, nomes e estilo estrutural; Bandit, pip-audit e detect-secrets foram adicionados a CI.
- Bancos Firebird, uploads e logs locais deixaram de ser versionados, sem apagar os arquivos locais.
- Adicionado modulo de laudos tecnicos com rascunho, finalizacao, PDF privado, hash, fotos, revisoes e cancelamento.
- Integracao de laudos com ordens de servico.
- Adicionados healthchecks `/healthz` e `/readyz`.
- Adicionado tratamento separado de erros HTML/API.
- Adicionados Flask-Migrate/Alembic incremental e migracao inicial do modulo de laudos.
- Adicionados Dockerfile, Compose dev/prod e exemplos de ambiente.
- Adicionados testes iniciais de laudos, healthchecks, erros, uploads e configuracao de migracao.
- Adicionado CI inicial, Ruff e separacao de requirements dev/prod.
