# Scripts Operacionais

Este diretorio contem scripts versionados de apoio a operacao do Zokyo.

## Backup do Banco

Script:

```text
scripts/backup_database.py
```

Ele le `DATABASE_URL` do ambiente ou do arquivo `.env`, executa `mysqldump`, compacta o dump em `.sql.gz`, gera um arquivo `.json` de metadados sem senha e remove backups locais antigos conforme politica de retencao.

### Requisitos

- Python 3.11+;
- cliente MySQL/MariaDB instalado com `mysqldump` disponivel no `PATH`;
- `DATABASE_URL` configurado.

### Uso Basico

Na raiz do projeto:

```bash
python scripts/backup_database.py
```

Por padrao, os arquivos sao gravados em:

```text
backups/
```

Esse diretorio nao deve ser versionado.

### Opcoes Uteis

```bash
# escolher destino
python scripts/backup_database.py --output-dir /var/backups/zokyo

# manter backups locais por 30 dias
python scripts/backup_database.py --keep-days 30

# informar caminho do mysqldump
python scripts/backup_database.py --mysqldump /usr/bin/mysqldump

# gerar .sql sem gzip
python scripts/backup_database.py --no-compress
```

### Cron

Exemplo diario as 03:00:

```cron
0 3 * * * cd /var/www/zokyo && /var/www/zokyo/venv/bin/python scripts/backup_database.py --output-dir /var/backups/zokyo --keep-days 30 >> /var/log/zokyo_backup.log 2>&1
```

### Restauracao

Para um backup compactado:

```bash
gunzip -c backups/zokyo_zokyo_YYYYMMDD_HHMMSS.sql.gz | mysql -u zokyo -p
```

Para um backup sem compactacao:

```bash
mysql -u zokyo -p < backups/zokyo_zokyo_YYYYMMDD_HHMMSS.sql
```

Teste restauracoes periodicamente em ambiente separado.
