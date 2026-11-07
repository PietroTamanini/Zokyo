# Retenção e Eliminação — Plano Técnico

**Status:** proposta para validação jurídica/contábil  
**Base:** LGPD Arts. 15, 16 e 18, VI; regras legais específicas devem prevalecer.

## Regras propostas

| Categoria | Retenção proposta | Pós-prazo | Observação |
|---|---|---|---|
| Tokens de recuperação | 90 dias conforme política atual, sujeito a revisão | Hard delete | Não registrar token bruto |
| Tokens de portal | 90 dias após expiração/revogação conforme política atual | Hard delete | Manter somente auditoria mínima |
| Notificações enviadas | 90 dias conforme política atual | Remover destinatário, mensagem, vínculo com OS e erro; manter chave de idempotência e horário | `manual_required`, `failed`, `pending` e `retry` ficam fora da limpeza até terem tratamento operacional |
| Conta/sessões | Vigência + prazo de segurança a definir | Revogar e eliminar sessões | Preservar eventos necessários a incidente |
| Clientes | Contrato + obrigação/defesa a validar | Anonimizar ou eliminar campos | Não apagar histórico obrigatório sem análise |
| OS/laudos/fotos/assinaturas | Prazo contratual, fiscal e de defesa a validar | Bloqueio parcial + anonimização | Possível dado sensível em texto livre |
| Financeiro/cobranças | Prazo fiscal/bancário/contratual a validar | Bloqueio e depois eliminação | Não reutilizar para marketing |
| Consentimentos/DSAR | Prazo de prova e responsabilização a validar | Retenção mínima da evidência | Responder titular sobre retenção |
| Auditoria/incidentes | Incidente: mínimo 5 anos; demais logs a definir | Eliminação segura | Res. 15/2024, Art. 10 |
| Uploads temporários/importações | 24 horas após upload, ou imediatamente após importação concluída; prazo operacional a validar | Exclusão do arquivo temporário | Não manter banco de origem sem finalidade; falhas podem exigir nova tentativa dentro da janela |
| Backups | Janela operacional aprovada por infra/jurídico | Expiração criptografada | Garantir descarte também em cópias |

## Implementação necessária

1. Criar `RetentionRule` por entidade, finalidade, base legal, prazo e ação.
2. Diferenciar `HARD_DELETE`, `ANONYMIZE`, `BLOCK_AND_RETAIN` e crypto-shredding.
3. Job diário idempotente, com dry-run, aprovação, relatório e log imutável.
4. Suspender eliminação quando houver obrigação legal, disputa, incidente ou hold jurídico.
5. Responder ao titular informando o que foi eliminado e o que foi bloqueado (Art. 18, VI).
6. Testar cascatas, storage, réplicas e backups em staging antes de ativar.

**Não ativar exclusão automática** até os prazos serem aprovados.

A categoria `user_sessions` está disponível no painel global por assistência, inicialmente desativada. Depois de um prazo em dias ser aprovado e ativado, o job elimina apenas sessões da assistência cuja expiração ou revogação ocorreu antes do limite configurado; sessões ainda ativas e sessões de outras assistências ficam preservadas. A operação registra empresa, categoria e quantidade na auditoria. Sessões de super admin sem `organization_id` não são abrangidas por essa política; ainda precisam de regra própria antes da operação real. O scheduler local do protótipo permanece desligado, portanto cadastrar a categoria não executa limpeza.

Exceção técnica já implementada: os arquivos **temporários de importação externa** são removidos após commit bem-sucedido e os abandonados há mais de 24 horas são limpos por job diário (e no próximo upload). Essa limpeza não altera clientes, OS, laudos, dados financeiros ou documentos definitivos; os prazos dessas categorias continuam sem aprovação/automação.

A categoria `notifications` do painel global, quando ativada após aprovação, limpa somente notificações `sent` mais antigas que o prazo e ainda não limpas. A migration `20261107_0051` acrescenta `redacted_at`. A limpeza remove destinatário, payload, vínculo com OS e erro em uma transação com evento de auditoria agregado por empresa/categoria/quantidade. O registro conserva ID, estado, horários, canal, tipo e chave de idempotência para impedir reenvio acidental do mesmo evento. Não é eliminação integral de todos os metadados; revisar a necessidade e o prazo deles antes de produção. Registros `manual_required` e `failed` continuam disponíveis para ação humana.
