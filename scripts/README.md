# Scripts operacionais

## Suportados

- `backup_database.py`: dump MariaDB com metadata e SHA-256.
- `restore_database.py`: valida e restaura dump em destino explicitamente informado.
- `backup_storage.py`: backup/verificacao do storage privado com manifesto.
- `test_laudo_concurrency.py`: prova de numeracao concorrente no MariaDB.
- `analyze_cplus_schema.py`: gera documentacao do schema Firebird informado localmente.

Sempre execute backup e restore com credenciais de ambiente, em janela controlada e primeiro em banco descartavel. Consulte `docs/BACKUP_RESTORE.md`.

## Compatibilidade legada

`migrate_constraints.py`, `migrate_clientes_cpf_cnpj_numero.py` e `migrate_laudos.py` sao ferramentas de recuperacao de versoes anteriores ao Alembic. Nao fazem parte da instalacao atual e nao devem ser executadas sem diagnostico e backup.

Instalacoes atuais usam exclusivamente:

```bash
flask --app wsgi:app db upgrade
flask --app wsgi:app db check
```
