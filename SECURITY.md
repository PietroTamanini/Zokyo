# Security Policy

## Reportar vulnerabilidades

Este projeto ainda nao possui canal publico formal. Enquanto isso, reporte vulnerabilidades diretamente ao mantenedor do repositorio, sem abrir issue publica com detalhes exploraveis.

Inclua:

- descricao do impacto;
- passos de reproducao;
- versao/commit afetado;
- evidencias sem expor dados reais de clientes.

## Segredos

Nunca versionar:

- `.env`;
- tokens WhatsApp;
- chaves de API;
- dumps de banco;
- backups;
- fotos/PDFs de clientes.

## Status

O projeto tem protecoes basicas de CSRF, CSP, sessoes, rate limiting de login, upload privado e auditoria. Ainda faltam RBAC granular, 2FA, recuperacao de senha e testes de seguranca amplos.
