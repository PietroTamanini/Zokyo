# Matriz de auditoria das mutacoes

Estado revisado em 2026-09-15. Esta matriz cobre rotas HTTP mutantes (`POST`, `PUT`, `PATCH` e `DELETE`) e diferencia o log geral `EventoLog` de trilhas especializadas do dominio.

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
| Autenticacao e sessoes | login, 2FA, logout, revogacao, recuperacao de senha, renovacao de token e primeiro acesso | `EventoLog` para sucesso, falha de 2FA, seguranca e sessao | Coberto nos fluxos centrais |
| Usuarios e permissoes | CRUD, convite, aceite, revogacao, troca de senha e matriz de permissao | `EventoLog` | Coberto nos fluxos centrais |
| Clientes e fornecedores | CRUD e arquivamento HTML/API | `EventoLog` | Coberto |
| OS pelo painel | criacao, edicao, itens, servicos, desconto, faturamento, pagamento, status, baixa e exclusao | `EventoLog` + `OSHistorico` | Coberto nos fluxos centrais |
| OS pela API | criacao, edicao, exclusao, itens, servicos, anotacoes e reservas | `EventoLog` + `OSHistorico`/movimentos | Coberto nos fluxos centrais |
| Estoque | produto, ajuste, lote, reserva e consumo | `EventoLog` + `InventoryMovement` | Coberto nos fluxos centrais |
| Financeiro | CRUD, pagamento, conciliacao, cobranca e gateway | `EventoLog` no painel, API e conciliacao | Coberto nos fluxos centrais; gateway ainda requer homologacao real |
| Laudos | rascunho, fotos, finalizacao, revisao e cancelamento | `LaudoEvento` | Coberto pela trilha especializada; avaliar espelho resumido em `EventoLog` |
| Configuracao e templates | configuracao geral, dashboard, OS, WhatsApp, templates e retry | `EventoLog` | Coberto nos fluxos persistentes |
| Portal | link, decisao de orcamento, aceite e rejeicoes publicas com token valido | `EventoLog` no servico de portal + `OSHistorico` | Coberto nos fluxos centrais |
| Privacidade | consentimento, exportacao, anonimizacao e retencao | modelos de consentimento/solicitacao + `EventoLog` | Coberto nos fluxos centrais; prazos finais dependem de aprovacao juridica |
| Relatorios salvos | criar e excluir | `EventoLog` | Coberto |
| Plataforma e assinatura | planos, assinatura, checkout, cancelamento e webhooks | `EventoLog` + `BillingEvent` | Coberto nos fluxos centrais; credenciais e cobrança real ainda requerem homologacao |
| Importacao externa | teste, preview e commit | `EventoLog` no commit | Coberto para a mutacao real; etapas de leitura nao exigem evento de mutacao |

## Lacunas priorizadas

Nenhuma lacuna automatizavel conhecida permanece na matriz central. As pendencias restantes dependem de ambiente real, credenciais, homologacao humana ou decisao juridica/comercial.

## Evidencia automatizada atual

- `tests/test_audit_tenancy.py` garante que `registrar()` usa o tenant autenticado e respeita tenant explicito fora de requisicao.
- Testes de paginas e APIs confirmam eventos nos fluxos centrais de clientes, OS, estoque, financeiro, usuarios e configuracao.
- `tests/test_core_api.py::test_crud_financeiro_api_gera_evento_log_sem_descricao_livre` confirma eventos de criacao, edicao e exclusao no CRUD financeiro da API, com tenant correto e sem copiar a descricao livre da transacao.
- `tests/test_core_api.py` cobre eventos gerais da API de estoque para criacao, edicao, exclusao, ajuste e recebimento de lote, mantendo justificativas livres apenas em `InventoryMovement`.
- `tests/test_os_routes_edges.py::test_os_api_cobre_criacao_atualizacao_checklist_pdf_whatsapp_e_assinatura` confirma eventos gerais da API de OS para criacao, edicao, exclusao, pecas e reservas, com tenant correto e sem copiar defeitos/observacoes livres.
- `tests/test_privacy.py` confirma eventos gerais de consentimento, exportacao e anonimizacao sem copiar nome, documento ou e-mail do titular.
- `tests/test_relatorios.py` confirma eventos de criacao e exclusao de relatorios salvos sem copiar nome do relatorio ou destinatario.
- `tests/test_billing.py` confirma eventos administrativos e de webhook para planos, assinaturas, checkout e cancelamento sem copiar documento, ids externos, tokens ou payloads.
- `tests/test_password_reset.py`, `tests/test_core_api.py`, `tests/test_route_edges.py` e `tests/test_pages_smoke.py::test_api_v1_login_e_regeneracao_token_bearer` confirmam recuperacao/reset de senha, aceite de convite, troca de senha pela API e regeneracao de token sem copiar e-mail, token ou senha.
- `tests/test_portal.py` confirma evento de seguranca para decisao publica negada com token valido, sem copiar token nem dados internos da OS.
- Testes de laudos validam a trilha especializada `LaudoEvento`.

A matriz central esta integralmente concluida para as lacunas automatizaveis conhecidas nesta revisao. Novas rotas mutantes devem acrescentar `EventoLog` ou trilha especializada equivalente e testes de modulo, tipo, tenant e ausencia de dados sensiveis.
