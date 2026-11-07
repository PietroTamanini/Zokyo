# Chaves e recuperação de dados cifrados

Estado em 2026-11-06: há criptografia de campos, índices cegos e backups cifrados. A gestão real das chaves, criptografia do disco do servidor e rotação de produção ainda precisam de implantação e evidências. O código **não** oferece rotação transparente de `SECRET_KEY`, `ENCRYPTION_SALT` ou `BLIND_INDEX_KEY`.

Em `FLASK_ENV=production`, o código recusa o salt legado e a chave implícita dos índices cegos: `ENCRYPTION_SALT` e `BLIND_INDEX_KEY` precisam estar explícitos. Se um ciphertext não autenticar, a leitura falha com `FieldDecryptionError`; nunca trate esse erro como campo vazio.

Desde a migration `0049`, novas gravações de pedidos de titulares e incidentes cifram identificadores, campos de texto livre e snapshots do histórico com `EncryptedText`. A migration amplia colunas, mas não reescreve registros legados: valores sem prefixo continuam sendo lidos para compatibilidade e podem permanecer em claro no banco e em backups antigos. O índice de e-mail em claro dos pedidos é removido. Antes de usar dados reais migrados, faça inventário dos registros legados e uma operação de recriptografia com backup, janela de manutenção e revisão da preservação do histórico append-only; não altere revisões protegidas silenciosamente.

O comando `privacy-encryption-audit --strict` contabiliza valores em claro e tenta decriptar todos os valores com prefixo nas colunas de pedidos, incidentes e seus históricos, sem imprimir conteúdo. Ele falha se algum ciphertext estiver ilegível, se houver legado em claro no modo estrito ou se o banco/schema estiver indisponível. Isso valida a chave atual para esses campos no banco consultado; não cobre backups, colunas fora do inventário ou a legitimidade do tratamento. Execute também restore controlado antes de operação real.

Desde `0052`, destinatário, corpo JSON e último erro das notificações também são cifrados. A migration reescreve as linhas legadas dessas três colunas usando `SECRET_KEY` e `ENCRYPTION_SALT` vigentes; o comando de auditoria inclui os campos. A perda dessas chaves impede ler mensagens ainda pendentes. Backups anteriores à migração não são recriptografados por ela.

Desde `0055`, IP e navegador das sessões, além de nome/IP do signatário de OS, também usam `EncryptedText`. A migration reescreve linhas legadas e o scanner estrito inspeciona essas colunas. Perder `SECRET_KEY`/`ENCRYPTION_SALT` impede ler as informações exibidas ao usuário e usadas como evidência da assinatura. A migration não protege arquivos ou backups já criados.

## Inventário operacional

| Segredo | Uso | Processo que precisa recebê-lo | Consequência da perda |
|---|---|---|---|
| `SECRET_KEY` e `ENCRYPTION_SALT` | Chave derivada para `EncryptedText`/`EncryptedJSON` e sessões | `app`, `scheduler`, manutenção que lê campos | Campos e notificações cifrados ficam ilegíveis; sessões podem ser invalidadas |
| `BLIND_INDEX_KEY` | HMAC para busca por CPF, CNPJ, telefone e e-mail | `app`, `scheduler`, migrações que recalculam índices | Busca exata existente deixa de corresponder |
| `BACKUP_ENCRYPTION_KEY` | AES-GCM dos dumps e uploads | Apenas `backup` e `backup-storage`; restore controlado | Backups cifrados ficam irrecuperáveis |
| Credenciais MariaDB | Migração, execução e backup | Separadas conforme `docs/DEPLOY.md` | Indisponibilidade ou acesso indevido ao banco |

## Procedimento antes de produção

1. Gere cada segredo aleatoriamente fora do repositório. Guarde versões e cópias de recuperação em cofre separado do servidor e dos backups; restrinja quem pode ler ou alterar cada um.
2. Ative criptografia do disco/volume do servidor e dos destinos externos. O temporário em claro de backup usa o filesystem do contêiner durante a execução; proteja também o disco que o hospeda.
3. Registre quem tem acesso, data de criação, versão e teste de recuperação, sem colocar valores em logs, chamados ou arquivos versionados.
4. Rode backup cifrado de banco e uploads, restaure em ambiente isolado com as chaves guardadas e registre o resultado. Prove que um operador sem acesso ao cofre não recebe a chave de backup no contêiner web.

## Rotação e incidente

- **Backup:** uma chave nova pode proteger os próximos backups. Preserve a chave antiga enquanto qualquer backup antigo estiver retido; valide restore de ambas as gerações antes de descartar a antiga. Os sidecars atuais não identificam versão de chave, então registre manualmente a associação entre data/arquivo e versão no cofre.
- **Campos cifrados:** mudar `SECRET_KEY` ou `ENCRYPTION_SALT` sem recriptografar os valores existentes quebra a leitura. O código agora lança `FieldDecryptionError` em vez de devolver campo vazio. Prepare migração reversível, backup íntegro, janela de manutenção e verificação de amostras antes de trocar esses valores. **Não execute rotação direta em produção.**
- **Índices cegos:** mudar `BLIND_INDEX_KEY` exige recalcular todos os índices com os valores ainda legíveis. Não troque a chave isoladamente.
- **Comprometimento:** interrompa o uso da chave exposta, preserve evidências, avalie o alcance dos dados e execute o runbook de incidentes em `.lgpd/incidents/runbook.md`. Não apague a única versão capaz de ler registros ou backups ainda necessários.

Pendência técnica: implementar versões de chave por ciphertext/backup, migração de recriptografia com rollback e verificação automatizada, e evidenciar um cofre e a criptografia do host em produção.
