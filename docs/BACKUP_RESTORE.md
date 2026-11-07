# Backup e restore

Estado revisado em 2026-11-06: scripts, criptografia, manifestos e validações automatizadas existem. Um dump MariaDB local foi restaurado em banco descartável; a cadeia de auditoria conferiu 26/26 eventos e os seis triggers estavam presentes. O banco descartável e o dump temporário foram removidos. Backup externo agendado e restore com dados de produção ainda precisam ser configurados e comprovados antes do go-live.

## Banco

Em produção, gere o backup **já criptografado**:

```bash
docker compose -f docker-compose.prod.yml --profile maintenance run --rm backup
```

O serviço de manutenção `backup` usa a conta de migração para incluir triggers e rotinas e grava no volume dedicado `backups_data`; ele não inicia com `app` e precisa de agendamento externo. O comando requer `BACKUP_ENCRYPTION_KEY`, escreve o dump em claro apenas em diretório temporário privado, cifra com AES-256-GCM, decripta uma cópia para conferir o SHA-256 e publica somente `.sql.gz.enc` e `.enc.json`. O arquivo temporário em claro é removido ao final. Configure retenção e cópia externa dos dois artefatos; a chave deve permanecer em cofre separado do backup.

Fora do Compose, execute `python scripts/backup_secure.py --output-dir backups` com `DATABASE_URL` da conta de backup/migração e a chave no ambiente ou em `--env-file` protegido.

O comando legado abaixo continua útil para diagnóstico local, mas não produz backup cifrado:

```bash
python scripts/backup_database.py --output-dir backups --keep-days 14
```

Esse comando grava um dump **sem criptografia** no diretório informado. Restrinja o diretório, criptografe o arquivo antes de copiá-lo para fora do servidor e remova o dump em claro após validar a cópia criptografada. A existência de `BACKUP_ENCRYPTION_KEY` não ativa criptografia automática neste comando.

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

Defina `RESTORE_DATABASE_URL` no ambiente do processo apontando para um banco descartável, com credenciais de migração/restore. O nome do banco de destino deve ser diferente daquele registrado no metadata do backup. Não passe a URL com senha como argumento de linha de comando.

```bash
python scripts/restore_database.py --backup backups/zokyo_banco_DATA.sql.gz.enc
```

Para `.enc`, o restaurador exige `BACKUP_ENCRYPTION_KEY`, confere tamanho/SHA-256 do arquivo cifrado, decripta em diretório temporário privado, confere o SHA-256 do dump e remove o arquivo em claro após o restore. O mesmo comando continua aceitando dumps legados `.sql`/`.sql.gz` para recuperação controlada.

O restaurador exige destino explícito e recusa um nome de banco igual ao do backup sem `--confirm-in-place`. A restauração no banco operacional requer janela de manutenção e a flag explícita `--confirm-in-place`; nesse caso, retire `RESTORE_DATABASE_URL` do ambiente para usar `DATABASE_URL` apenas depois de conferir o destino.

## Validacao obrigatoria

Um backup só deve ser considerado válido depois de restaurado em ambiente descartável e comparado com:

- quantidade de registros principais;
- abertura de OS;
- download de PDF de laudo;
- abertura de fotos privadas;
- login administrativo.
- `flask --app wsgi:app audit-verify` sem inconsistências;
- presença dos triggers `trg_eventos_log_no_update`, `trg_eventos_log_no_delete`, `trg_incident_revision_no_update`, `trg_incident_revision_no_delete`, `trg_request_revision_no_update` e `trg_request_revision_no_delete` no banco restaurado.

## Operacao

- Agende banco e storage diariamente no scheduler do host.
- Copie apenas arquivos criptografados e o metadata correspondente para uma conta externa com retenção e imutabilidade.
- Monitore falhas e a idade do backup mais recente.
- Execute uma restauracao trimestral conforme `DISASTER_RECOVERY.md`.
- Em produção, execute `mysqldump` com a conta de migração/backup que possui acesso a triggers e rotinas. A conta `APP_DB_USER` é só de execução e não deve ser usada para gerar ou restaurar dumps estruturais.

Depois de gerar **os dois** backups, valide pares, hashes e idade por tipo antes da cópia externa:

```bash
python scripts/backup_offsite.py --source backups --remote s3:zokyo/producao --require-kind database-backup --require-kind private-storage-backup --require-audit-anchor --max-age-hours 26
```

Esse comando exige `rclone` e um remoto configurado no host, copia `.enc`, `.enc.json` e `.audit-anchor.json` e usa `--immutable`. O comando não cria o remoto nem agenda a execução; configure credenciais, retenção e alerta fora do repositório. A ausência de qualquer backup obrigatório ou de âncora recente, ou metadata divergente, impede a cópia. O diretório passado em `--source` deve conter os arquivos reais do volume `backups_data`; um diretório local vazio chamado `backups` não é equivalente ao volume Docker.

O scheduler de produção grava uma âncora de auditoria sem dados pessoais no volume `backups_data` após cada verificação diária íntegra. Ela contém horário UTC, quantidade conferida, último ID e hash da ponta verificada. `flask --app wsgi:app audit-verify --anchor-dir /app/backups` compara a última âncora local com a cadeia atual. A cópia externa preserva a âncora ao lado dos backups cifrados; mantenha versão/imutabilidade e acesso separado do banco operacional. A âncora local ou no mesmo volume não é prova externa por si só. O protótipo local não ativa o scheduler nem possui remoto externo configurado.
# Storage privado

Em produção, faça backup cifrado dos uploads locais e PDFs pelo serviço de manutenção:

```bash
docker compose -f docker-compose.prod.yml --profile maintenance run --rm backup-storage
```

O serviço lê `uploads_data` somente para leitura e grava no volume `backups_data`. A chave `BACKUP_ENCRYPTION_KEY` deve estar configurada. Ele cria somente `zokyo_uploads_DATA.tar.gz.enc` e seu `.json` com tamanho e SHA-256. O manifesto com nomes de arquivos fica dentro do arquivo cifrado. O arquivo em claro só existe no diretório temporário privado durante a operação. Links simbólicos na origem causam erro para evitar backup incompleto.

Fora do Compose, execute:

```bash
python scripts/secure_storage.py create --source instance/uploads --output-dir backups
```

Verifique um backup sem escrever arquivos:

```bash
python scripts/secure_storage.py restore --archive backups/zokyo_uploads_DATA.tar.gz.enc --verify-only
```

Restaure primeiro em um diretório vazio e descartável:

```bash
python scripts/secure_storage.py restore --archive backups/zokyo_uploads_DATA.tar.gz.enc --destination /tmp/zokyo-restore
```

O restaurador confere SHA-256 do arquivo cifrado, autenticidade AES-GCM, manifesto, tamanho e hash de cada arquivo antes de extrair. O destino de uploads ativos ou um diretório não vazio exige `--confirm-in-place`; use essa opção somente em janela de recuperação, após verificar o backup e o caminho absoluto do destino. A conta normal do serviço `backup-storage` monta os uploads em modo de leitura e não pode restaurá-los diretamente.

O serviço cobre apenas arquivos no volume local `uploads_data`. Se a instalação usar S3 ou outro storage externo, configure backup, retenção, restauração e evidências daquele serviço separadamente. Agende banco e uploads, copie ambos os artefatos cifrados e seus metadados para armazenamento externo e teste uma restauração periódica.

O comando legado abaixo gera arquivo **sem criptografia** e deve ficar restrito ao desenvolvimento ou à recuperação controlada:

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
python scripts/restore_database.py --backup backups/zokyo_banco_DATA.sql.gz.enc --verify-only
```

Restaure em banco descartável com `RESTORE_DATABASE_URL` configurada:

```bash
python scripts/restore_database.py --backup backups/zokyo_banco_DATA.sql.gz.enc
```

O comando usa `RESTORE_DATABASE_URL` para teste isolado ou `DATABASE_URL` apenas com `--confirm-in-place`, usa arquivo temporário de credenciais com permissão restrita e não inclui senha nos argumentos do processo. Backups corrompidos ou com metadata divergente são rejeitados antes da conexão ao banco. Depois do restore, execute `audit-verify` e confira os triggers no **banco restaurado**; não use a conexão do banco principal para essa verificação.
