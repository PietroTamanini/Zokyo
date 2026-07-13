# Permissoes

O projeto usa uma matriz central em `app/utils/permissions.py`. Perfis fornecem permissoes base e cada usuario pode receber listas persistidas de `permissoes_extra` e `permissoes_negadas`. Permissoes desconhecidas sao recusadas pela API. Administradores mantem acesso total para evitar bloqueio acidental da administracao.

## Perfis atuais

- `admin`: administracao completa.
- `operacional`: rotina de OS, atendimento e laudos.
- `financeiro`: financeiro e indicadores financeiros.
- `cadastro`: cadastros e consultas operacionais.
- `consulta`: leitura/consulta.

## Laudos

| Acao | Perfis atuais |
| --- | --- |
| Visualizar/listar | `admin`, `operacional`, `cadastro`, `consulta` |
| Criar rascunho | `admin`, `operacional` |
| Editar rascunho | `admin`, `operacional` |
| Upload/remocao de fotos em rascunho | `admin`, `operacional` |
| Finalizar e gerar PDF | `admin`, `operacional` |
| Baixar PDF | `admin`, `operacional`, `cadastro`, `consulta` |
| Duplicar/criar revisao | `admin`, `operacional` |
| Cancelar | `admin` |

## Permissoes atomicas

- `laudos.view`
- `laudos.create`
- `laudos.edit_draft`
- `laudos.finalize`
- `laudos.download_pdf`
- `laudos.revise`
- `laudos.cancel`
- `laudos.admin_templates`

O backend usa `has_permission()` e `permission_required()`. O frontend pode ocultar botoes, mas nunca e a fonte da decisao de acesso. A API administrativa de usuarios aceita `permissoes_extra` e `permissoes_negadas` como listas validadas e expoe o catalogo em `GET /api/permissoes`.
