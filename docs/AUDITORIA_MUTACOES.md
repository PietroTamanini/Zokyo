# Matriz de auditoria das mutacoes

Estado revisado em 2026-09-03. Esta matriz cobre rotas HTTP mutantes (`POST`, `PUT`, `PATCH` e `DELETE`) e diferencia o log geral `EventoLog` de trilhas especializadas do dominio.

## Invariantes

- Todo evento deve usar o `organization_id` da sessao autenticada ou recebê-lo explicitamente em rotinas sem sessao.
- Eventos nunca podem ser associados ao tenant `1` apenas por fallback quando existe um tenant autenticado.
- Operacoes negadas podem gerar evento de seguranca, mas nao devem parecer mutacoes concluidas.
- Senhas, tokens, documentos completos e segredos nao entram em `operacao` ou `descricao`.
- Exclusoes logicas, conciliacoes, pagamentos, mudancas de status e alteracoes de permissao sao eventos auditaveis.
- Laudos, estoque e notificacoes podem complementar `EventoLog` com trilhas imutaveis especificas.

## Cobertura por dominio

| Dominio | Entradas mutantes principais | Trilha atual | Estado |
|---|---|---|---|
| Autenticacao e sessoes | login, 2FA, logout, revogacao e primeiro acesso | `EventoLog` para sucesso, falha de 2FA, seguranca e sessao | Parcial: revisar recuperacao/troca de senha e renovacao de token |
| Usuarios e permissoes | CRUD, convite, revogacao e matriz de permissao | `EventoLog` | Parcial: aceite de convite e troca de senha pela API |
| Clientes e fornecedores | CRUD e arquivamento HTML/API | `EventoLog` | Coberto |
| OS pelo painel | criacao, edicao, itens, servicos, desconto, faturamento, pagamento, status, baixa e exclusao | `EventoLog` + `OSHistorico` | Coberto nos fluxos centrais |
| OS pela API | criacao, edicao, exclusao, itens, servicos, anotacoes e reservas | `EventoLog` em parte + `OSHistorico`/movimentos | Parcial |
| Estoque | produto, ajuste, lote, reserva e consumo | `EventoLog` em parte + `InventoryMovement` | Parcial: formalizar eventos gerais da API |
| Financeiro | CRUD, pagamento, conciliacao, cobranca e gateway | `EventoLog` no painel e conciliacao | Parcial: CRUD da API |
| Laudos | rascunho, fotos, finalizacao, revisao e cancelamento | `LaudoEvento` | Coberto pela trilha especializada; avaliar espelho resumido em `EventoLog` |
| Configuracao e templates | configuracao geral, dashboard, OS, WhatsApp, templates e retry | `EventoLog` | Coberto nos fluxos persistentes |
| Portal | link, decisao de orcamento e aceite | `EventoLog` no servico de portal + `OSHistorico` | Parcial: registrar emissao do link no log geral ja ocorre; validar eventos publicos negados |
| Privacidade | consentimento, anonimizacao e retencao | modelos de consentimento/solicitacao + `EventoLog` em retencao | Parcial: espelhar consentimento e anonimizacao no log geral |
| Relatorios salvos | criar e excluir | sem `EventoLog` comprovado | Pendente |
| Plataforma e assinatura | planos, assinatura, checkout, cancelamento e webhooks | eventos de billing em parte | Parcial: definir espelho administrativo sem registrar payload sensivel |
| Importacao externa | teste, preview e commit | `EventoLog` no commit | Coberto para a mutacao real; etapas de leitura nao exigem evento de mutacao |

## Lacunas priorizadas

1. Adicionar `EventoLog` ao CRUD financeiro da API.
2. Completar eventos gerais na API de OS: criar, editar, arquivar, itens, servicos e reservas.
3. Espelhar ajustes e recebimentos de estoque da API, mantendo `InventoryMovement` como fonte detalhada.
4. Registrar consentimento e anonimizacao sem incluir dados pessoais no texto do evento.
5. Auditar criacao/exclusao de relatorios salvos.
6. Definir eventos administrativos seguros para planos, assinaturas, cancelamentos e webhooks.
7. Cobrir aceite de convite, troca/recuperacao de senha e renovacao de token com eventos de seguranca apropriados.

## Evidencia automatizada atual

- `tests/test_audit_tenancy.py` garante que `registrar()` usa o tenant autenticado e respeita tenant explicito fora de requisicao.
- Testes de paginas e APIs confirmam eventos nos fluxos centrais de clientes, OS, estoque, financeiro, usuarios e configuracao.
- Testes de laudos validam a trilha especializada `LaudoEvento`.

A matriz somente pode ser marcada como integralmente concluida quando as lacunas acima tiverem testes que confirmem modulo, tipo, tenant e ausencia de dados sensiveis.
