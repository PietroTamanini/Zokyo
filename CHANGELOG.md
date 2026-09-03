# Changelog

## Unreleased

### Corrigido

- Eliminada falha de concorrência do rate limit global no MariaDB, com incremento atômico e retry limitado para conflitos transitórios reconhecidos.
- Tornada determinística a auditoria E2E do modal de clientes quando a tela vazia oferece mais de um link com o mesmo texto.

### Verificado

- 201 testes Python, lint, compilação e validação JavaScript aprovados em 2026-08-27.
- Auditoria autenticada das telas em compact, mobile, tablet, desktop e wide, incluindo runtime, HTTP 500, overflow e WCAG.
- Teste local com 150 requisições simultâneas sem erro após a correção de concorrência.

### Documentação

- Adicionado `IA.md` como memória técnica viva para continuidade entre agentes e desenvolvedores.
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
