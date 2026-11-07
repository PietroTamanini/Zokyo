# Operador: Hosting, MariaDB, Redis e infraestrutura

## Contexto atualizado

O servidor principal, MariaDB e Redis foram informados como mantidos localmente no Brasil, na infraestrutura do responsável. Não há transferência internacional identificada para essa infraestrutura principal. Ainda assim, a Zokyo deve formalizar o papel de operadora perante cada assistência, controles de segurança, acesso remoto, backups, descarte e resposta a incidentes. S3 ou outro storage externo só deve ser habilitado após avaliação própria de país, suboperadores e salvaguardas.

- **Razão social/país:** infraestrutura local do responsável / Brasil; razão social e titularidade formal a confirmar
- **Finalidade:** executar aplicação, banco, sessões, arquivos e backups.
- **Dados:** potencialmente todos os dados pessoais e cópias de produção.
- **Tier:** Crítico
- **DPA:** pendente; bloqueia produção até assinatura.
- **Transferência:** não identificada para o servidor principal no Brasil; país/região e suboperadores de backups ou serviços externos a confirmar; aplicar Arts. 33–36 e Res. 19/2024 se internacional.
- **Evidências necessárias:** criptografia, MFA, RBAC, acesso de suporte, logs, backup, restore, eliminação e incidentes.
- **Owner:** Infra/SRE
- **Próxima revisão:** trimestral após aprovação.
