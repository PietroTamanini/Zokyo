# Gap Analysis e Plano de Remediação — 2026-11-06

> Diagnóstico técnico inicial. Não é parecer jurídico. A classificação de controlador/operador, bases legais e textos públicos deve ser revisada pelo responsável jurídico/encarregado.

## Resumo

- **7 críticos:** governança/ROPA/base legal, canal DSAR, resposta a incidentes, operadores/transferências, retenção ampla e proteção de menores.
- **9 altos:** política pública, encarregado, imutabilidade de auditoria, exportação completa, eliminação/anonimização, criptografia, storage/backups e dados sensíveis.
- **4 médios:** minimização, treinamento, inventário de acessos e evidências de segurança.
- **Aplicabilidade ECA Digital por fluxo pendente:** há inventário técnico preventivo; faltam público real, classificação dos sites e avaliação jurídica conforme os critérios da ANPD.

## Matriz de gaps

| ID | Item | Status | Evidência | Severidade | Ação |
|---|---|---|---|---|---|
| LGPD-01 | ROPA/inventário de tratamentos | YELLOW | `.lgpd/ROPA.md` foi criado como rascunho técnico, sem aprovação dos controladores | Crítica | Validar finalidades, papéis, bases e prazos conforme Art. 37 |
| LGPD-02 | Base legal por atividade | RED | Não há matriz aprovada por fluxo. O ledger de consentimento agora guarda versão e referência e rejeita alteração/exclusão, mas não há coleta pública direta nem checagem de consentimento nos tratamentos opcionais | Crítica | Documentar Art. 7, Art. 10 e Art. 11 quando aplicável; implementar coleta direta e bloquear usos opcionais sem consentimento válido |
| LGPD-03 | Canal e workflow DSAR | YELLOW | Canal público, limite dedicado de 10 POST/hora por IP configurável com pseudônimo HMAC no bucket, triagem super admin, método/protocolo/horário de verificação manual, vínculo auditável com cliente/empresa, prazo, alertas diários, histórico append-only e registro de entrega implementados; limitador global/API e bloqueio de login também usam pseudônimos. Comprovação externa e atendimento completo dependem de operação | Crítica | Homologar Art. 18, resposta em 15 dias do Art. 19, II e eventual prazo em dobro ATPP da Res. 2/2022, Art. 14 |
| LGPD-04 | Incidentes | YELLOW | Runbook, workflow, horários, aviso de triagem após 24h e histórico append-only em `0045` implementados; envio, plantão, segregação de privilégios e evidências operacionais ainda pendentes | Crítica | Completar Art. 48 e Res. 15/2024; testar notificação, tabletop e retenção dos registros |
| LGPD-05 | Operadores e contratos | RED | Há inventário técnico de sete serviços e modelo de DPA em `.lgpd/vendors/`, mas nenhum contrato assinado/validado foi comprovado | Crítica | Validar operadores e formalizar DPAs conforme Art. 39 |
| LGPD-06 | Transferência internacional | RED | Há avaliações preliminares em `.lgpd/transfers/`, mas país efetivo, fluxo ativado e mecanismo contratual não foram comprovados por fornecedor | Crítica | Validar Arts. 33–36 e Res. 19/2024, Anexo II antes de ativar transferência |
| LGPD-07 | Política de privacidade pública | YELLOW | Rascunho v1.0 existe; a rota pública só encaminha para URL HTTPS de documento aprovado após preenchimento institucional e confirmação de revisão. No protótipo, permanece despublicada | Alta | Preencher dados oficiais, revisar juridicamente, publicar documento versionado aprovado e manter histórico |
| LGPD-08 | Encarregado e canal | RED | Não há designação/contato público confirmado | Alta | Designar e publicar conforme Art. 41 e Res. 18/2024; se ATPP baixo risco, manter canal mesmo com eventual dispensa formal (Res. 2/2022, Art. 11) |
| LGPD-09 | Retenção e eliminação | YELLOW | Automação cobre tokens, conteúdo pessoal de notificações enviadas (`0051`), sessões expiradas/revogadas das assistências após prazo aprovado e arquivos temporários de importação externa (24h ou após commit). A política de sessões começa desativada; sessões de super admin sem empresa não entram nessa regra. Falhas/envios manuais pendentes e dados definitivos aguardam tratamento/prazos aprovados | Alta | Definir prazos por categoria, tratamento de pendências e mecanismos de eliminação/anonimização conforme Arts. 15, 16 e 18, VI |
| LGPD-10 | Exportação de titular | YELLOW | ZIP administrativo inclui cadastro com e-mail, OS, coletas, laudos, transações relacionadas, consentimentos, pedidos vinculados e manifesto de fotos/arquivos; consultas exigem empresa e cliente. Custos, comissões e payload do gateway ficam fora. SHA-256 do ZIP final entra no evento auditado, cabeçalho e pedido vinculado (migration `0050`), mas não comprova entrega; revisão de textos/imagens, portabilidade e cobertura integral ainda dependem de homologação | Alta | Conferir registros/arquivos restantes, terceiros em texto livre, controle de identidade, formato e trilha de entrega do Art. 18 |
| LGPD-11 | Anonimização | YELLOW | Ação administrativa foi renomeada para remoção de dados cadastrais, sem prometer anonimização; OS, laudos e coletas bloqueiam a ação. Auditoria, consentimentos, solicitações, fotos, assinaturas, arquivos e backups ainda podem reidentificar | Alta | Mapear dependências e validar anonimização real conforme Art. 5, XI e Art. 18, IV/VI |
| LGPD-12 | Auditoria imutável | YELLOW | Cadeia serializada e protegida por triggers; produção separa usuário DML de migração, validado em usuário temporário local. O job diário registra sucesso append-only e pode publicar âncora de hash no volume de backups. A cópia rclone agora aceita/exige âncora recente; ainda falta configurar destino externo e comprovar cópia, scheduler e retenção real | Alta | Operar scheduler, copiar âncoras para armazenamento independente/imutável, preservar logs/backups e auditar root/host conforme Art. 6, X e Res. 15/2024, Art. 10 |
| LGPD-13 | Criptografia e chaves | YELLOW | `EncryptedText` protege pedidos/incidentes desde `0049`; `EncryptedJSON` e `0052` protegem notificações. A migration `0055` cifrou IP/navegador de sessões e nome/IP de assinaturas; o scanner estrito cobre as novas colunas. No MariaDB local, 17 sessões foram verificadas sem claro/ilegíveis; não havia assinaturas para backfill real. Cofre, criptografia do host, outros legados/backups e rotação de produção não foram comprovados | Alta | Completar inventário de campos/arquivos, recriptografar legados restantes e formalizar cofre/KMS, rotação e backup de chaves conforme Art. 46 |
| LGPD-14 | Uploads/backups | YELLOW | Banco e uploads locais: backup cifrado/verificado com serviços opcionais de produção; restore descartável de banco recuperou auditoria 26/26 e seis triggers. Cópia externa, agendamento, S3, ciclo de vida e restore de produção não comprovados | Alta | Agendar backups cifrados e cópia externa, validar storage privado/ACL/ciclo de vida e restore periódico com evidência (Art. 46) |
| LGPD-15 | Dados sensíveis | YELLOW | Pedidos/incidentes novos têm texto livre cifrado desde `0049` e notificações desde `0052`; laudos, saúde/defeito e outros documentos ainda podem conter dados sensíveis em campos e arquivos não cobertos | Alta | Minimizar campos, classificar Art. 5, II, aplicar bases do Art. 11 e avaliar RIPD do Art. 38 |
| LGPD-16 | Menores | RED | Responsável informou que o sistema pode ser acessado por menores; inventário de fluxos criado, mas enquadramento e mecanismos proporcionais não foram comprovados | Crítica enquanto pendente | Confirmar público e conteúdo por fluxo; implementar idade, responsável, controles parentais e antiperfilização conforme aplicabilidade e `.lgpd/eca-digital.md` |
| LGPD-17 | Minimização | YELLOW | Novos eventos de cliente, usuário, coleta, cobrança e incidente usam IDs em vez de nome/e-mail/título; limitador global/API e bloqueio de login passaram a usar pseudônimos HMAC (`0053` limpa contadores antigos, `0054` converte bloqueios antigos). Logs de acesso novos de Gunicorn/Nginx omitem IP, URL, referer e navegador; tracebacks da aplicação passam pelo mascaramento. Registros históricos, logs de erro do proxy, sessões e outros campos livres ainda podem conter dados pessoais | Média | Revisar necessidade/finalidade e demais pontos de log/exportação conforme Art. 6, I–III |
| LGPD-18 | Acessos privilegiados | YELLOW | Aberturas de páginas globais, auditoria, operações, configurações e ficha de privacidade por empresa geram evento imutável com usuário/escopo. Exportação e remoção cadastral exigem POST, CSRF e motivo; pedido do titular precisa de vínculo verificado ao cliente e investigação precisa de incidente da empresa, com IDs no evento. Suporte, duplicidade e minimização agora exigem código de protocolo externo registrado no evento, mas o código ainda é autodeclarado; justificativa das leituras e revisão periódica pendem | Média | Integrar protocolo/decisão a registro verificável, limitar por necessidade e revisar periodicamente (Art. 6, VII, VIII e X) |
| LGPD-19 | Treinamento/governança | RED | Não há evidência versionada de treinamento ou programa Art. 50 | Média | Treinamento, política interna e evidência de aceite conforme Arts. 46 e 50 |
| LGPD-20 | Evidências de segurança | YELLOW | Há documentação operacional, mas não evidência contínua de pentest, restore e revisão | Média | Calendário de testes, correções e evidências conforme Art. 46 |

## Ações imediatas — fazer primeiro

1. Designar encarregado, canal e responsável por privacidade — **Art. 41; Res. 18/2024**.
2. Criar canal DSAR com triagem, autenticação, prazos e registro — **Arts. 18–19**.
3. Publicar runbook de incidente e registro de 5 anos — **Art. 48; Res. 15/2024, Arts. 6, 9 e 10**.
4. Inventariar operadores, contratos e localização de dados — **Art. 39; Arts. 33–36; Res. 19/2024**.
5. Definir retenção por categoria e bloquear eliminação incompatível com obrigação legal — **Arts. 15–16 e 18, VI**.
6. Mapear fluxos acessíveis por menores e aplicar o plano ECA Digital antes de ampliar o acesso público — **Lei 15.211/2025, Arts. 9, 17, 18, 22, 24, 26 e 31, conforme aplicabilidade**.

## Decisões de contexto incorporadas

- As assistências são controladoras dos dados de seus clientes, funcionários, atendimentos e operação.
- A Zokyo é principalmente operadora desses dados; é controladora independente dos dados próprios do SaaS, como contratação, cobrança, segurança, suporte e obrigações legais.
- A infraestrutura principal será um servidor local no Brasil. A análise de operadores e transferências continua necessária para SMTP, Asaas, Meta, Cloudflare, S3, Sentry e qualquer serviço externo ativado.

## Próximas 2–4 semanas

6. Gerar `data-map.md`, matriz de bases legais e ROPA — **Arts. 6, 7, 10, 11 e 37**.
7. Atualizar política de privacidade e avisos por contexto — **Art. 9**.
8. Completar exportação, correção, anonimização, eliminação e revogação — **Art. 18**.
9. Implementar auditoria hash-encadeada e revisar vazamento de dados livres — **Art. 6, X; Art. 46**.
10. Formalizar chaves, storage privado, backups e restore — **Art. 46**.

## Próximo trimestre

11. Avaliar e produzir RIPD para laudos, portal, dados sensíveis ou decisões automatizadas — **Art. 38; Res. 2/2022, Art. 4**.
12. Treinar equipe e publicar programa de governança — **Art. 50**.
13. Executar pentest, tabletop de incidente e revisão de privilégios — **Art. 46**.
14. Fechar decisão sobre ECA Digital conforme público real — **Lei 15.211/2025**.

## Resultado L4 — operadores, DPAs e transferências

- **7 operadores/serviços inventariados:** hosting/MariaDB/Redis, SMTP, Asaas, Meta WhatsApp, Cloudflare, S3 e Sentry opcional.
- **Crítico:** hosting/banco/storage e Asaas.
- **Alto:** SMTP, Meta, Cloudflare e Sentry.
- **DPA comprovado:** 0/7 no repositório.
- **Transferências com país e cláusulas comprovados:** 0/7.
- **Bloqueio:** não usar operador em produção com DPA ausente ou transferência internacional sem mecanismo dos Arts. 33–36 e Res. 19/2024.
- **Artefatos:** fichas em `.lgpd/vendors/`, modelo em `.lgpd/vendors/dpa-template.md` e avaliações em `.lgpd/transfers/`.

## Responsáveis sugeridos

- **Produto/engenharia:** DSAR, retenção, logs, minimização e controles técnicos.
- **Infra/SRE:** chaves, storage, backups, incidentes e evidências.
- **Operação:** atendimento ao titular, treinamento e validação de retenção.
- **Jurídico/encarregado:** bases legais, ROPA, política, DPA, transferências, RIPD e ECA Digital.
- **Direção/controlador:** aprovar finalidades, riscos residuais, prazos e publicações.
