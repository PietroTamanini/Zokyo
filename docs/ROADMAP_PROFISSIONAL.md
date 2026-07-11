# Roadmap para ficar 100% profissional

## Critico antes de producao

- Criar baseline Alembic completo do schema legado.
- Remover dependencia de `db.create_all()` tambem em dev/testes.
- Mover scheduler para processo separado, cron ou worker dedicado.
- Revisar CSP de producao e remover dependencias CDN do layout autenticado.
- Implementar recuperacao de senha segura com token de uso unico.
- Criar RBAC granular persistido por permissao, nao apenas perfis.
- Ampliar testes de acesso indevido, CSRF, login, logout e usuario inativo.
- Validar Docker/Compose em ambiente limpo.
- Automatizar backup e restore com teste real de restauracao.

## Laudos

- Adicionar QR Code visual ao PDF.
- Criar thumbnails separados das fotos.
- Implementar reordenacao visual de fotos.
- Criar limpeza/deteccao de arquivos orfaos.
- Adicionar PDF/comprovante marcado como cancelado.
- Criar templates administraveis de laudo.
- Ampliar testes de concorrencia da numeracao.
- Testar limite de fotos, arquivo grande, path traversal e download indevido.
- Criar API JSON para laudos, se necessario.

## SaaS e multiempresa

- Criar tabela `organizacoes`.
- Adicionar `organization_id` em usuarios, clientes, OS, estoque, financeiro e configuracoes.
- Fazer backfill seguro para organizacao padrao.
- Centralizar filtro obrigatorio por tenant.
- Bloquear `organization_id` enviado pelo navegador sem validacao.
- Criar testes de vazamento entre empresas.
- Separar painel global/admin.

## Produto

- Portal do cliente.
- Acompanhamento publico/seguro de OS.
- Aprovacao de orcamento.
- Notificacoes.
- Relatorios gerenciais.
- Exportacao CSV, Excel e PDF com permissao.
- Estados vazios, onboarding e ajuda.

## Comercial

- Modelar planos e limites.
- Criar provider fake/sandbox de cobranca.
- Preparar webhooks idempotentes.
- Auditoria de assinatura, upgrade, downgrade e cancelamento.
- Nao escolher gateway real sem decisao do proprietario.

## Seguranca e LGPD

- 2FA para administradores.
- Logs estruturados com request ID.
- Sentry opcional.
- Metricas basicas.
- Politica de retencao.
- Exportacao de dados.
- Anonimizacao/exclusao quando legalmente possivel.
- Registro de consentimento.
- Politica formal para documentos e fotografias.

## Qualidade

- Aumentar cobertura de testes, principalmente rotas legadas.
- Adicionar testes de migracoes.
- Auditar dependencias no CI.
- Secret scanning robusto.
- Lint gradual mais amplo.
- Validar PWA/cache para nao guardar dados sensiveis.

