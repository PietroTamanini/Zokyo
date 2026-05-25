# Scripts Operacionais

Este diretório contém scripts versionados de apoio à operação do Zokyo.

## backup_database.py

Faz backup do banco MySQL/MariaDB.

Ele lê `DATABASE_URL` do ambiente ou do arquivo `.env`, executa `mysqldump`, compacta o dump em `.sql.gz`, gera um arquivo `.json` de metadados sem senha e remove backups locais antigos conforme política de retenção.

### Requisitos

- Python 3.11+;
- cliente MySQL/MariaDB instalado com `mysqldump` disponível no `PATH`;
- `DATABASE_URL` configurado.

### Uso Básico

Na raiz do projeto:

```bash
python scripts/backup_database.py
```

Por padrão, os arquivos são gravados em:

```
backups/
```

Esse diretório não deve ser versionado.

### Opções Úteis

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

Exemplo diário às 03:00:

```cron
0 3 * * * cd /var/www/zokyo && /var/www/zokyo/venv/bin/python scripts/backup_database.py --output-dir /var/backups/zokyo --keep-days 30 >> /var/log/zokyo_backup.log 2>&1
```

### Restauração

Para um backup compactado:

```bash
gunzip -c backups/zokyo_zokyo_YYYYMMDD_HHMMSS.sql.gz | mysql -u zokyo -p
```

Para um backup sem compactação:

```bash
mysql -u zokyo -p < backups/zokyo_zokyo_YYYYMMDD_HHMMSS.sql
```

Teste restaurações periodicamente em ambiente separado.

---

## migrate_constraints.py

Aplica melhorias de integridade referencial e índices ao banco de dados.

Execute **após** fazer backup e após o primeiro `python app.py` (que cria as tabelas via `db.create_all()`).

### Quando executar

- na primeira instalação em produção, logo após iniciar a aplicação pela primeira vez;
- ao subir o sistema em um banco existente que ainda não tenha recebido o script;
- nunca precisa ser executado novamente — o script é **idempotente**.

### Uso

```bash
python scripts/migrate_constraints.py
```

O script usa o mesmo `DATABASE_URL` do `.env`. Cada operação exibe resultado individual (`✅` ou aviso de item já existente).

### O que o script faz

- adiciona constraints de chave estrangeira e índices ausentes nas tabelas principais;
- opera com `IF NOT EXISTS` ou trata erros de duplicata, portanto pode ser executado múltiplas vezes com segurança;
- não apaga nem altera dados existentes.
