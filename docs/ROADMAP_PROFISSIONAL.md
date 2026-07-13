# Roadmap profissional

Atualizado em 2026-07-12. Evidencias detalhadas ficam em `IMPLEMENTATION_STATUS.md`.

## Entregue

- Numeracao de laudos validada com 24 transacoes simultaneas no MariaDB.
- Restore integral validado em banco descartavel, com tabelas e contagens comparadas.
- Compose de producao validado com MariaDB, migracao, Gunicorn, scheduler e Nginx; WhatsApp possui imagem e perfil opcionais proprios.
- CSP sem `unsafe-inline` para estilos nas respostas HTTP.
- Templates versionados de laudo e categorias fotograficas obrigatorias.
- Portal do cliente com token hash, expiracao, revogacao e aprovacao auditada de orcamento.
- Fila WhatsApp persistente com idempotencia, historico, retry e fallback manual.
- Relatorios gerenciais e exportacoes CSV, XLSX e PDF protegidos por permissao.
- Painel global SaaS, planos, limites, assinatura e webhook sandbox idempotente.
- Exportacao do titular, solicitacoes LGPD, consentimento e anonimizacao conservadora.

## Situacao

Nao ha itens internos pendentes neste roadmap.

- Onboarding individual, checklist operacional e Central de Ajuda foram entregues.
- Retencao configuravel foi entregue em modo conservador, inativa por padrao e condicionada a aprovacao explicita.
- A API de laudos permanece deliberadamente HTML-first: o prompt determina criar contrato JSON somente quando existir consumidor definido.

Escolhas que dependem do proprietario, assessoria juridica ou fornecedor externo nao sao backlog de engenharia e estao registradas em `DECISOES_EXTERNAS.md`.
