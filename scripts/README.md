# Scripts operacionais

## Suportados

- `backup_database.py`: dump MariaDB com metadata e SHA-256.
- `backup_crypto.py`: criptografia autenticada dos artefatos de backup.
- `backup_offsite.py`: envio do backup criptografado para destino externo configurado.
- `restore_database.py`: valida e restaura dump em destino explicitamente informado.
- `backup_storage.py`: backup/verificacao do storage privado com manifesto.
- `load_test.py`: smoke/load test HTTP com limite configurável de latência p95.
- `test_laudo_concurrency.py`: prova de numeracao concorrente no MariaDB.
- `start-zokyo-local.ps1` e `start-zokyo-local.cmd`: inicialização assistida no Windows.

Sempre execute backup e restore com credenciais de ambiente, em janela controlada e primeiro em banco descartável. Consulte [Backup e restore](../docs/BACKUP_RESTORE.md), [Recuperação de desastre](../docs/DISASTER_RECOVERY.md) e [Política operacional](../docs/SUPORTE_OPERACAO.md).

Instalacoes atuais usam exclusivamente:

```bash
flask --app wsgi:app db upgrade
flask --app wsgi:app db check
```
