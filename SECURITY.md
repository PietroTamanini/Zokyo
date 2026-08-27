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

O projeto possui CSRF, CSP com nonce, sessões revogáveis, rate limiting persistente e concorrente, upload privado, auditoria, RBAC granular, isolamento multiempresa, 2FA administrativo, recuperação de senha por token de uso único e cobertura automatizada de segurança. Em 2026-08-27, o limitador global foi validado com 150 requisições simultâneas no MariaDB local.

A entrada em produção ainda depende de HTTPS, cofre de segredos, 2FA obrigatório configurado, backup externo com restore comprovado, alertas reais, SMTP e testes no host final. Consulte [Checklist de go-live](docs/GO_LIVE.md) e [Política de suporte e operação](docs/SUPORTE_OPERACAO.md).
