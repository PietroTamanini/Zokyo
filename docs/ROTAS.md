# Rotas

## HTML

- `/` - dashboard.
- `/ajuda` - onboarding, checklist e Central de Ajuda autenticada.
- `/login` - login.
- `/primeiro-acesso` - cadastro do primeiro administrador.
- `/os` - listagem de ordens de servico.
- `/os/nova` - abertura de OS.
- `/os/<id>` - detalhe da OS.
- `/clientes` - clientes.
- `/estoque` - estoque.
- `/fornecedores` - fornecedores.
- `/financeiro` - financeiro.
- `/usuarios` - usuarios.
- `/configuracoes` - configuracoes da empresa.
- `/configuracoes/notificacoes` - historico e retentativas de notificacoes (administrador).
- `/privacidade/retencao` - prazos e ativacao aprovada da retencao operacional (administrador).
- `/logs` - auditoria.
- `/laudos` - listagem de laudos.
- `/laudos/novo?os_id=<id>` - novo laudo vinculado a OS.
- `/laudos/<id>` - detalhe do laudo.
- `/laudos/<id>/editar` - edicao de rascunho.
- `/laudos/<id>/pdf` - download autenticado do PDF.
- `/laudos/verificar/<token>` - verificacao publica minima, se habilitada.
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

Requisicoes mutantes exigem CSRF.
