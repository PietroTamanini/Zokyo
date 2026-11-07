# Rotas

Estado revisado em 2026-11-02. As páginas principais foram auditadas com Playwright em cinco tamanhos; aliases legados permanecem por compatibilidade e devem ser removidos somente com plano de migração.

## HTML

- `/` - dashboard gerencial com filtros por período, indicadores financeiros e operacionais.
- `/dashboard` - alias para o dashboard principal.
- `/ajuda` - onboarding, checklist e Central de Ajuda autenticada.
- `/login` - login.
- `/primeiro-acesso` - cadastro do primeiro administrador.
- `/os` - listagem de ordens de servico.
- `/os/nova` - abertura de OS.
- `/os/<id>` - detalhe da OS, incluindo histórico contextual de mensagens.
- `POST /os/<id>/notificacoes/<notification_id>/reenviar` - cria nova tentativa para uma mensagem vinculada à OS (administrador ou operacional).
- `/clientes` - clientes.
- `/estoque` - estoque.
- `/fornecedores` - fornecedores.
- `/financeiro` - financeiro.
- `/financeiro/caixa` - fechamento de caixa (abertura, movimentacoes, conferencia e fechamento diario).
- `/usuarios` - usuarios.
- `/configuracoes` - configuracoes da empresa.
- `/configuracoes/site/` - configuração da landing pública da empresa.
- `/configuracoes/site/verify` - verificação do domínio customizado.
- `/onboarding` - onboarding guiado da empresa.
- `/configuracoes/notificacoes` - historico e retentativas de notificacoes (administrador).
- `/privacidade/retencao` - prazos e ativacao aprovada da retencao operacional (administrador).
- `/privacidade/solicitacao` - canal público de direitos do titular.
- `/privacidade/solicitacao/<slug>` - canal de direitos vinculado a uma assistência.
- `/privacidade/solicitacoes` - triagem global de solicitações pelo super admin.
- `/privacidade/incidentes` - registro global de incidentes de privacidade pelo super admin.
- `/privacidade/configuracao` - governança institucional e encarregado pelo super admin.
- `/privacidade/politica` - redireciona para a URL HTTPS de documento aprovado após configuração institucional e confirmação de revisão; responde 503 enquanto não publicado.
- `/logs` - auditoria.
- `/laudos` - listagem de laudos.
- `/laudos/novo?os_id=<id>` - novo laudo vinculado a OS.
- `/laudos/<id>` - detalhe do laudo.
- `/laudos/<id>/editar` - edicao de rascunho.
- `/laudos/<id>/pdf` - download autenticado do PDF.
- `/laudos/verificar/<token>` - verificacao publica minima, se habilitada.
- `/portal/os/<token>` - portal público da OS por token.
- `/` em host público - landing da empresa resolvida pelo domínio.
- `/` com usuário autenticado - dashboard da empresa.
- `/healthz` - healthcheck do processo.
- `/readyz` - readiness com verificacao do banco.

## APIs existentes

- `/api/os`
- `/api/clientes`
- `/api/pecas`
- `/api/fornecedores`
- `/api/transacoes`
- `/api/usuarios`
- `/api/defeitos`
- `/api/logs`
- `/api/whatsapp/status`
- `/api/whatsapp/teste`
- `/api/public/os-consulta`
- `/api/cash/*`
- `/api/inventario/*`
- `/api/v1/client/*`
- `/api/importacao/bancos/*`
- `/healthz`, `/readyz`, `/metrics`

Requisicoes mutantes exigem CSRF.

## Privacidade por empresa no painel global

- `GET /platform/companies/<organization_id>/settings/privacy/clients` — lista e busca de clientes da empresa selecionada para o super admin.
- `GET /platform/companies/<organization_id>/settings/privacy/clients/<client_id>` — ficha de privacidade e histórico vinculado.
- `POST /platform/companies/<organization_id>/settings/privacy/clients/<client_id>/export` — exportação administrativa com CSRF, motivo e SHA-256 do ZIP no evento auditado e em `X-Export-SHA256`; não conclui automaticamente solicitação de titular.
- `POST /platform/companies/<organization_id>/settings/privacy/clients/<client_id>/remove-registration` — exige CSRF e motivo categorizado; remove identificadores cadastrais quando não há OS, laudo ou coleta vinculada, sem declarar anonimização integral.

Essas rotas exigem super admin sem vínculo com empresa. O `organization_id` da URL é validado junto ao `client_id` em todas as operações.
