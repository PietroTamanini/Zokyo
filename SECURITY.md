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

O projeto possui CSRF, CSP com nonce, sessoes revogaveis, rate limiting de login, upload privado, auditoria, RBAC granular, 2FA administrativo, recuperacao de senha por token de uso unico e cobertura automatizada de seguranca. A entrada em producao ainda depende de HTTPS, cofre de segredos, backup externo validado, alertas reais e testes no host final.
