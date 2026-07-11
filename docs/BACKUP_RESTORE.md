# Backup e restore

## Banco

```bash
python scripts/backup_database.py --output-dir backups --keep-days 14
```

## Uploads e PDFs

Inclua no backup:

- `instance/uploads/os_fotos`
- `instance/uploads/reports`

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

## Pendencias

- script automatizado de restore em ambiente descartavel;
- criptografia opcional de backups;
- envio para storage externo;
- politicas de retencao por tipo de dado.
