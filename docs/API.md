# API

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

O modulo de laudos atual e HTML-first. Downloads e fotos sao rotas autenticadas HTML. Uma API JSON dedicada para laudos ainda e pendente.
