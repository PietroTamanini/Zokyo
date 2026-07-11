# Configuracao

Copie `.env.example` para `.env` em desenvolvimento e ajuste os valores locais.

## Obrigatorias

- `SECRET_KEY`: chave forte para sessoes e criptografia derivada.
- `DATABASE_URL`: URL SQLAlchemy do MySQL/MariaDB.

Em producao, `SECRET_KEY` e `DATABASE_URL` sao validadas no startup.

## Recomendadas

- `ENCRYPTION_SALT`: salt base64 aleatorio para segredos persistidos em `Configuracao`.
- `WKHTMLTOPDF_PATH`: caminho absoluto do wkhtmltopdf quando usado pelo PDF legado de OS.
- `REPORTS_UPLOAD_FOLDER`: pasta privada dos laudos. Se vazia, usa `instance/uploads/reports`.
- `REPORTS_PUBLIC_VERIFICATION`: habilita/desabilita a rota publica de verificacao de laudos.
- `PROXY_COUNT`: numero de proxies confiaveis na frente do Flask.

## Geradores

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

## Laudos

Arquivos sensiveis de laudos nao devem ficar em `static/`. Use armazenamento privado no filesystem ou, futuramente, uma implementacao compativel com S3.
