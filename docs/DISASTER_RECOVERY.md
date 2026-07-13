# Recuperacao de desastre

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
python scripts/backup_database.py --output-dir backups --keep-days 14
python scripts/backup_storage.py create --source instance/uploads --output backups/storage.tar.gz
python scripts/backup_crypto.py encrypt backups/storage.tar.gz backups/storage.tar.gz.enc
```

Use o mesmo comando de criptografia no dump mais recente. Copie somente arquivos `.enc` e seus metadados para storage externo. Nunca envie a chave junto com o backup.

## Restauracao

1. Declare a janela de manutencao e bloqueie novas escritas.
2. Baixe uma copia criptografada para um host descartavel.
3. Descriptografe e valide hashes antes de qualquer restauracao.
4. Restaure primeiro em MariaDB e storage descartaveis.
5. Execute migrations, `/readyz`, login, abertura de OS, fotos e PDFs.
6. Registre responsavel, horarios, arquivos e hashes utilizados.
7. Somente depois repita a restauracao no ambiente definitivo.

```bash
python scripts/backup_crypto.py decrypt backup.sql.gz.enc backup.sql.gz
python scripts/restore_database.py --backup backup.sql.gz --verify-only
python scripts/backup_storage.py restore --archive storage.tar.gz --destination /tmp/zokyo-restore
```

## Rollback

- Aplicacao: mantenha a imagem Docker anterior identificada por digest e redeploy essa imagem.
- Banco: migrations destrutivas exigem backup validado e janela dedicada; nao execute downgrade automatico em dados de producao.
- Em falha apos migration, preserve logs, interrompa escritas e restaure banco e storage do mesmo ponto temporal.

## Simulacao trimestral

Restaure a ultima copia em ambiente isolado, cronometre o procedimento e registre divergencias. A simulacao so e aprovada quando banco, anexos, login e fluxos essenciais funcionarem e os objetivos de RPO/RTO forem atendidos.
