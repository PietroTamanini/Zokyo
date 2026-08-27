# API

Estado revisado em 2026-08-27. As rotas documentadas possuem cobertura automatizada; integrações externas e consumidores reais ainda devem ser homologados antes de produção.

As APIs autenticadas usam `/api/*` e retornam JSON. Requisicoes `POST`, `PUT`, `PATCH` e `DELETE` exigem CSRF.

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

## Outros recursos

- Clientes: `/api/clientes`
- Pecas: `/api/pecas`
- Fornecedores: `/api/fornecedores`
- Financeiro: `/api/transacoes`
- Usuarios: `/api/usuarios`
- Defeitos padrao: `/api/defeitos`
- Logs: `/api/logs`

## Erros

APIs retornam:

```json
{"success": false, "erro": "Mensagem"}
```

## Laudos

O modulo de laudos atual e deliberadamente HTML-first. Downloads e fotos usam rotas autenticadas HTML; uma API JSON dedicada so deve ser criada quando houver consumidor externo definido.
