# Inventário de Operadores — L4

**Data:** 2026-11-06  
**Status:** o servidor principal foi informado como local, no Brasil. Isso reduz a hipótese de transferência internacional na infraestrutura principal, mas não substitui contrato/DPA com cada assistência e nem a análise dos serviços externos eventualmente ativados. Nenhum DPA, país ou certificação de serviço externo foi comprovado no repositório.

| Operador/serviço | Finalidade | Dados potenciais | Tier | DPA | País/transferência |
|---|---|---|---|---|---|
| Servidor local/MariaDB/Redis | Hospedagem, banco e sessão | Todos os dados do tenant | Crítico | Contrato/DPA operador-controlador pendente | Brasil, informado; sem transferência internacional identificada para a infraestrutura principal |
| SMTP | Convites, recuperação e notificações | Nome, e-mail, conteúdo contextual | Alto | Pendente | A confirmar |
| Asaas (se ativado) | Assinatura, cobrança e webhooks | Dados empresariais/financeiros | Crítico | Pendente | A confirmar |
| Meta WhatsApp Cloud API (se ativada) | Mensagens operacionais | Nome, telefone e mensagem | Alto | Pendente | A confirmar |
| Cloudflare/DNS (se ativado) | DNS, domínio e proteção | Domínio, IP e logs técnicos | Alto | Pendente | A confirmar |
| S3 compatível (se ativado) | Armazenamento de arquivos/backups | Laudos, fotos, assinaturas e cópias | Crítico | Pendente | A confirmar |
| Sentry (se ativado) | Erros e observabilidade opcional | Contexto técnico potencialmente pessoal | Alto | Pendente | A confirmar |

## Critério de bloqueio

Nenhum operador deve receber produção antes de confirmar papel, finalidade, DPA, suboperadores, segurança, auxílio a titulares, incidente, eliminação e base de transferência quando fora do Brasil (LGPD, Arts. 39, 42 e 46; Arts. 33–36; Res. 19/2024).

## Evidências a coletar

- Razão social/CNPJ, contrato e DPA assinado.
- Países de tratamento, suboperadores e regiões de armazenamento.
- Segurança, MFA, logs, certificações e histórico de incidentes.
- SLA de incidente de até 24h para permitir o prazo regulatório do controlador.
- Processo de exportação, eliminação e atestado ao término.
