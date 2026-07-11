# Permissoes

O projeto ainda usa perfis simples em `usuarios.nivel`. A matriz abaixo registra o comportamento atual e o alvo incremental para RBAC granular.

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

## Pendencia RBAC

Ainda falta transformar perfis em permissoes atomicas persistidas, por exemplo:

- `laudos.view`
- `laudos.create`
- `laudos.edit_draft`
- `laudos.finalize`
- `laudos.download_pdf`
- `laudos.revise`
- `laudos.cancel`
- `laudos.admin_templates`

O frontend pode ocultar botoes, mas a decisao de acesso deve continuar no backend.
