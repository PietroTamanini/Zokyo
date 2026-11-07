# Recuperacao de desastre

Estado revisado em 2026-11-06: os fluxos cifrados de banco e uploads locais foram testados em ambiente descartável; a recuperação externa e a operação no servidor de produção ainda precisam ser simuladas e documentadas.

## Objetivos

- RPO: no maximo 24 horas de dados, reduzido conforme a frequencia real dos backups.
- RTO: restaurar o servico essencial em ate 4 horas.
- Backups locais: 14 dias.
- Backups externos criptografados: 90 dias, com pelo menos uma copia imutavel.

Os objetivos devem ser revisados pelo proprietario conforme o volume e o impacto financeiro da operacao.

## Preparacao obrigatoria

1. Mantenha `SECRET_KEY`, `ENCRYPTION_SALT` e `BACKUP_ENCRYPTION_KEY` em um cofre externo.
2. Gere backups separados do MariaDB e de `instance/uploads`.
3. Criptografe os arquivos antes de copia-los para o destino externo.
4. Restrinja a conta de backup a gravacao, sem permissao para apagar copias historicas.
5. Monitore idade, tamanho e resultado dos backups.

## Execucao diaria

```bash
docker compose -f docker-compose.prod.yml --profile maintenance run --rm backup
docker compose -f docker-compose.prod.yml --profile maintenance run --rm backup-storage
```

Os dois serviços publicam somente arquivos `.enc` e respectivos metadados no volume `backups_data`. Agende ambos fora da aplicação, copie esses pares para storage externo e monitore a idade de cada tipo separadamente. Nunca envie a chave junto com o backup. Se houver S3 para anexos, mantenha uma rotina separada de recuperação e retenção daquele bucket.

Para copiar com `rclone` após os dois jobs, use `backup_offsite.py --require-kind database-backup --require-kind private-storage-backup` conforme [Backup e restore](BACKUP_RESTORE.md). O host precisa ter acesso ao volume de backups e um destino externo configurado; nenhum remoto foi homologado nesta revisão.

## Restauracao

1. Declare a janela de manutencao e bloqueie novas escritas.
2. Baixe uma copia criptografada para um host descartavel.
3. Descriptografe e valide hashes antes de qualquer restauracao.
4. Restaure primeiro em MariaDB e storage descartaveis.
5. Execute migrations, `/readyz`, login, abertura de OS, fotos e PDFs.
6. Registre responsavel, horarios, arquivos e hashes utilizados.
7. Somente depois repita a restauracao no ambiente definitivo.

```bash
python scripts/restore_database.py --backup backup.sql.gz.enc --verify-only
python scripts/secure_storage.py restore --archive storage.tar.gz.enc --verify-only
python scripts/secure_storage.py restore --archive storage.tar.gz.enc --destination /tmp/zokyo-restore
```

Para restaurar o banco em destino descartável, defina `RESTORE_DATABASE_URL` e execute `python scripts/restore_database.py --backup backup.sql.gz.enc`. Confira [Backup e restore](BACKUP_RESTORE.md) para as regras de destino ativo e a verificação de triggers/auditoria.

## Rollback

- Aplicacao: mantenha a imagem Docker anterior identificada por digest e redeploy essa imagem.
- Banco: migrations destrutivas exigem backup validado e janela dedicada; nao execute downgrade automatico em dados de producao.
- Em falha apos migration, preserve logs, interrompa escritas e restaure banco e storage do mesmo ponto temporal.

## Simulacao trimestral

Restaure a ultima copia em ambiente isolado, cronometre o procedimento e registre divergencias. A simulacao so e aprovada quando banco, anexos, login e fluxos essenciais funcionarem e os objetivos de RPO/RTO forem atendidos.
