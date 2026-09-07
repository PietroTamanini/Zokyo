# Backup e restore

Estado revisado em 2026-08-27: scripts, criptografia, manifestos e validações automatizadas existem. Backup externo agendado e restore com dados de produção ainda precisam ser configurados e comprovados antes do go-live.

## Banco

```bash
python scripts/backup_database.py --output-dir backups --keep-days 14
```

No Windows local com XAMPP e usuario sem permissao para `SHOW EVENTS`, use:

```powershell
.\venv\Scripts\python.exe scripts\backup_database.py --env-file .env --output-dir backups --mysqldump C:\xampp\mysql\bin\mysqldump.exe --extra-mysqldump-arg=--no-tablespaces --extra-mysqldump-arg=--skip-events
```

## Criptografia

Gere uma chave fora do servidor e guarde-a em um cofre de segredos:

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
export BACKUP_ENCRYPTION_KEY="valor-do-cofre"
python scripts/backup_crypto.py encrypt backups/arquivo.sql.gz backups/arquivo.sql.gz.enc
python scripts/backup_crypto.py decrypt backups/arquivo.sql.gz.enc /tmp/arquivo.sql.gz
```

A criptografia usa AES-256-GCM em blocos autenticados, suporta arquivos grandes e rejeita alteracoes antes de publicar o arquivo restaurado.

## Restore de banco

Backup compactado:

```bash
gunzip -c backups/arquivo.sql.gz | mysql -u zokyo -p zokyo
```

Backup sem compactacao:

```bash
mysql -u zokyo -p zokyo < backups/arquivo.sql
```

## Validacao obrigatoria

Um backup so deve ser considerado valido depois de restaurado em ambiente descartavel e comparado com:

- quantidade de registros principais;
- abertura de OS;
- download de PDF de laudo;
- abertura de fotos privadas;
- login administrativo.

## Operacao

- Agende banco e storage diariamente no scheduler do host.
- Copie apenas arquivos criptografados para uma conta externa com retencao e imutabilidade.
- Monitore falhas e a idade do backup mais recente.
- Execute uma restauracao trimestral conforme `DISASTER_RECOVERY.md`.
# Storage privado

Crie um backup dos uploads e PDFs com manifesto SHA-256:

```bash
python scripts/backup_storage.py create --source instance/uploads --output backups/storage.tar.gz
```

Verifique a integridade sem extrair:

```bash
python scripts/backup_storage.py restore --archive backups/storage.tar.gz --destination /tmp/zokyo-verify --verify-only
```

Restaure primeiro em um diretorio vazio e descartavel:

```bash
python scripts/backup_storage.py restore --archive backups/storage.tar.gz --destination /tmp/zokyo-restore
```

O restaurador rejeita caminhos fora do destino e links simbolicos. O teste automatizado `test_backup_storage_verifica_e_restaura` valida criacao, hashes e restauracao byte a byte.

## Banco de dados

Todo backup novo inclui tamanho e SHA-256 no metadata sidecar. Verifique antes de restaurar:

```bash
python scripts/restore_database.py --backup backups/zokyo_banco_DATA.sql.gz --verify-only
```

Restaure somente em banco descartavel ou durante janela de manutencao confirmada:

```bash
python scripts/restore_database.py --backup backups/zokyo_banco_DATA.sql.gz
```

O comando le `DATABASE_URL`, usa arquivo temporario de credenciais com permissao restrita e nao inclui senha nos argumentos do processo. Backups corrompidos ou com metadata divergente sao rejeitados antes da conexao ao banco.
