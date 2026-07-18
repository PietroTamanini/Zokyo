# Scripts operacionais

## Suportados

- `backup_database.py`: dump MariaDB com metadata e SHA-256.
- `restore_database.py`: valida e restaura dump em destino explicitamente informado.
- `backup_storage.py`: backup/verificacao do storage privado com manifesto.
- `test_laudo_concurrency.py`: prova de numeracao concorrente no MariaDB.

Sempre execute backup e restore com credenciais de ambiente, em janela controlada e primeiro em banco descartavel. Consulte `docs/BACKUP_RESTORE.md`.

Instalacoes atuais usam exclusivamente:

```bash
flask --app wsgi:app db upgrade
flask --app wsgi:app db check
```
