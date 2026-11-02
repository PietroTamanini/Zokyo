# API

Estado revisado em 2026-11-02. As rotas documentadas possuem cobertura automatizada e mutações auditadas nos fluxos centrais; integrações externas e consumidores reais ainda devem ser homologados antes de produção.

As APIs autenticadas usam `/api/*` e retornam JSON. Requisições `POST`, `PUT`, `PATCH` e `DELETE` exigem CSRF, exceto os fluxos bearer documentados.

## Ordens de servico

- `GET /api/os`
- `GET /api/os/<id>`
- `POST /api/os`
- `PUT /api/os/<id>`
- `DELETE /api/os/<id>`
- `POST /api/os/<id>/pecas`
- `DELETE /api/os/<id>/pecas/<peca_id>`
- `GET /api/os/<id>/pdf`
- `POST /api/os/<id>/whatsapp`

Ao alterar uma OS para `entregue`, o pagamento integral deve estar registrado. Se o lucro projetado for negativo, a API responde `409` com `code=loss_risk_confirmation_required`; após revisão consciente, repita a requisição com `confirm_loss_risk: true`. A confirmação fica registrada na auditoria geral sem copiar valores financeiros.

## Outros recursos

- Clientes: `/api/clientes`
- Pecas: `/api/pecas`
- Fornecedores: `/api/fornecedores`
- Dashboard gerencial: indicators de faturamento, receitas, despesas, lucro/margem, contas a receber, inadimplência, OS status, tempo médio de atendimento, serviços mais realizados, desempenho por período. Filtros por período (?period=last_month, etc.), suporta multi-tenant.
- Caixa / fechamento: `/api/cash/*` (sessoes, movimentos e relatorio)
- Inventário físico: `/api/inventario/*` (sessões, contagens, aprovação, fechamento e histórico)
- Usuarios: `/api/usuarios`
- Defeitos padrao: `/api/defeitos`
- Logs: `/api/logs`
- Consulta pública de OS: `POST /api/public/os-consulta`
- Portal bearer: `/api/v1/client/auth`, `/api/v1/client`, `/api/v1/client/os`, `/api/v1/client/compras`, `/api/v1/client/cobrancas`
- Importação de banco: `/api/importacao/bancos/*`
- Health e operação: `/healthz`, `/readyz`, `/metrics`, `/api/operations/status`

## Erros

APIs retornam:

```json
{"success": false, "erro": "Mensagem"}
```

## Laudos

O modulo de laudos atual e deliberadamente HTML-first. Downloads e fotos usam rotas autenticadas HTML; uma API JSON dedicada so deve ser criada quando houver consumidor externo definido.

## Tenancy e dados públicos

Rotas públicas não confiam em `organization_id` enviado pelo cliente. A empresa é resolvida pelo host, domínio/subdomínio validado, identificador explícito permitido ou por uma correspondência única em fixtures de teste. Em produção, múltiplas empresas exigem host ou empresa explícita.
