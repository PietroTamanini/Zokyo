# Mapa de Dados — Zokyo

**Versão:** v1 (reverse-engineering)  
**Data:** 2026-11-06  
**Owner global:** Encarregado/DPO — pendente de designação  
**Base:** código Flask, modelos SQLAlchemy, rotas, serviços, migrações e documentação do repositório.

## Papéis de tratamento

- **Assistência:** controladora dos dados de clientes, funcionários, OS, laudos, financeiro e comunicações da própria operação.
- **Zokyo:** operadora desses dados quando fornece hospedagem/software sob instrução da assistência.
- **Zokyo como controladora:** dados da relação comercial com a assistência, administradores da plataforma, cobrança da assinatura, segurança, suporte e obrigações legais próprias.
- A definição deve constar no contrato principal e no DPA; uma mesma atividade pode ter papéis diferentes conforme a finalidade.

> Este inventário técnico identifica tratamentos observáveis. As bases legais, papéis de controlador/operador, prazos e transferências precisam ser aprovados no L3/L4. “Possível sensível” significa que campos livres podem receber informação sensível; não significa que todo registro contenha dado sensível.

## Sistemas e repositórios

- **Banco principal:** MariaDB/SQLAlchemy; tabelas de usuários, clientes, OS, laudos, financeiro, privacidade, auditoria, billing e configurações.
- **Sessão/cache:** Redis opcional e sessões Flask/UserSession no banco.
- **Arquivos:** `instance/uploads`, storage privado de laudos/fotos/assinaturas/sites e S3 compatível opcional.
- **Logs:** `EventoLog`, logs de aplicação/Gunicorn, métricas/observabilidade e arquivos de importação.
- **Terceiros identificados:** SMTP, Asaas, Meta WhatsApp Cloud API, Cloudflare DNS, S3 compatível e Sentry opcional.

## Atividades de tratamento

### A001 — Conta, autenticação e segurança de acesso

| Campo | Valor |
|---|---|
| Slug | `a001-auth-account` |
| Finalidade | Criar contas, autenticar usuários, recuperar acesso, aplicar perfis e proteger sessões. |
| Base legal | Pendente no L3 — provável execução de contrato e segurança; ver `.lgpd/legal-basis.md`. |
| Titulares | Administradores globais, donos e funcionários das assistências. Menores: acesso possível, sem intenção de cadastro como público principal; avaliar proteção específica. |
| Dados | Nome, e-mail, senha em hash, perfil/permissões, TOTP criptografado, códigos de recuperação, sessões, IP/user-agent quando registrados. |
| Fonte | Cadastro, convite, login e ações do próprio usuário/administrador autorizado. |
| Sistemas | `usuarios`, `user_sessions`, `password_reset_tokens`, `user_invites`, sessão Flask/Redis, logs de segurança. |
| Compartilhamentos | Servidor local da Zokyo no Brasil; SMTP somente se ativado. Localização internacional de integrações externas: pendente. |
| Retenção | Tokens têm política parcial; conta, sessões e eventos sem prazo aprovado. |
| Segurança | Hash de senha, TOTP criptografado, RBAC/ABAC, rate limit, CSRF e revogação de sessão. |
| Alto risco | Não pela finalidade isolada; revisar se houver biometria, profiling ou grande escala. |
| Owner | Segurança/engenharia + encarregado. |

### A002 — Provisionamento de empresa, assinatura e cobrança

| Campo | Valor |
|---|---|
| Slug | `a002-tenant-billing` |
| Finalidade | Criar assistência, administrar domínio/plano, cobrar assinatura e operar o SaaS. |
| Base legal | Pendente no L3 — provável contrato, obrigação legal e proteção do crédito conforme o fluxo. |
| Titulares | Donos, responsáveis financeiros, administradores e contatos de empresas. |
| Dados | Nome empresarial, CNPJ, e-mail, telefone, endereço, plano, status, identificadores de gateway e eventos de cobrança. |
| Fonte | Super admin, empresa, Asaas e webhooks. |
| Sistemas | `organizations`, `configuracoes`, `organization_subscriptions`, `plans`, `billing_events`, logs. |
| Compartilhamentos | Asaas; SMTP; infraestrutura local brasileira; possivelmente contabilidade. DPA/localização de integrações pendentes. |
| Retenção | Billing e documentos fiscais dependem de obrigação legal; prazo formal pendente. |
| Segurança | Acesso global restrito, tenant isolation, logs resumidos e webhook token. |
| Alto risco | Não identificado; revisar volume e perfil financeiro. |
| Owner | Financeiro/plataforma + jurídico/encarregado. |

### A003 — Cadastro e atendimento de clientes

| Campo | Valor |
|---|---|
| Slug | `a003-customer-service` |
| Finalidade | Identificar cliente, prestar assistência técnica, comunicar atendimento e manter histórico. |
| Base legal | Pendente no L3 — provável contrato, legítimo interesse ou obrigação legal conforme caso. |
| Titulares | Clientes pessoa física, representantes de pessoa jurídica e contatos indicados. Menores: possível, com aplicação preventiva das salvaguardas pertinentes. |
| Dados | Nome, CPF/CNPJ, telefone, e-mail, CEP, endereço, cidade, UF, histórico de atendimento. |
| Fonte | Titular, funcionário, importação externa e integração autorizada. |
| Sistemas | `clientes`, índices cegos, `ordens_servico`, `os_historico`, notificações e logs. |
| Compartilhamentos | Equipe autorizada da assistência, Zokyo como operador, portal, SMTP/WhatsApp quando acionado. |
| Retenção | Sem política completa para cliente/histórico; definir por finalidade e obrigação legal. |
| Segurança | Isolamento por organização, RBAC/ABAC, criptografia de alguns campos e blind indexes. |
| Alto risco | Não por padrão; pode subir se houver larga escala, menores ou dados sensíveis. |
| Owner | Assistência contratante + produto/encarregado. |

### A004 — Ordem de serviço, laudo, fotos e assinatura

| Campo | Valor |
|---|---|
| Slug | `a004-service-orders-evidence` |
| Finalidade | Diagnosticar, reparar, documentar, autorizar, entregar e comprovar o serviço. |
| Base legal | Pendente no L3 — contrato, obrigação legal e proteção de direitos; Art. 11 se o texto livre contiver dado sensível. |
| Titulares | Clientes, funcionários/técnicos e terceiros mencionados em observações. Menores: possível, pendente. |
| Dados | Equipamento, série/IMEI, defeito, diagnóstico, solução, observações, laudos, fotos, assinatura, nome do signatário e valores. Texto livre pode conter saúde ou outros dados sensíveis. |
| Fonte | Cliente, técnico, upload, assinatura e integração/importação. |
| Sistemas | `ordens_servico`, `os_historico`, `laudos`, `laudo_fotos`, `order_signatures`, storage privado/S3, PDFs e notificações. |
| Compartilhamentos | Cliente/portal, equipe autorizada, Zokyo como operador, notificações e storage local/operador. |
| Retenção | Laudos, fotos, assinaturas e OS sem tabela de prazo aprovada; conciliar com obrigações e defesa de direitos. |
| Segurança | Controle por tenant, ACL/storage key, validação de upload, trilhas de OS e proteção de arquivos. |
| Alto risco | **Possível** — avaliar dados sensíveis em texto livre, larga escala e decisões/triagem; RIPD pendente. |
| Owner | Operação técnica + jurídico/encarregado. |

### A005 — Portal do cliente e consulta pública de OS

| Campo | Valor |
|---|---|
| Slug | `a005-customer-portal` |
| Finalidade | Permitir consulta, aprovação, assinatura, acompanhamento e comunicação sem acesso ao painel interno. |
| Base legal | Pendente no L3 — contrato/execução do serviço e segurança. |
| Titulares | Clientes e pessoas com acesso a token; menores: possível, pendente. |
| Dados | Token de portal, OS, status, valores, equipamento, mensagens, assinatura e identificadores técnicos. |
| Fonte | Sistema interno, cliente e ações via link/token. |
| Sistemas | `portal_tokens`, rotas portal, `order_signatures`, OS, PDFs e logs de segurança. |
| Compartilhamentos | Cliente portador do link, SMTP/WhatsApp, storage. |
| Retenção | Tokens possuem política parcial; conteúdo da OS/assinatura segue prazo pendente. |
| Segurança | Tokens revogáveis/expiráveis, escopo por OS/tenant, links privados e logs resumidos. |
| Alto risco | Possível se links vazarem, envolverem menores ou grande escala; avaliar RIPD. |
| Owner | Produto/segurança + assistência. |

### A006 — Mensagens, notificações e WhatsApp

| Campo | Valor |
|---|---|
| Slug | `a006-communications` |
| Finalidade | Enviar atualizações de OS, cobranças, convites e mensagens operacionais. |
| Base legal | Pendente no L3; separar mensagens contratuais de marketing/consentimento. |
| Titulares | Clientes, funcionários, administradores e destinatários informados. |
| Dados | Nome, e-mail, telefone/WhatsApp, conteúdo contextual de OS/cobrança e status de entrega. |
| Fonte | Cadastro, OS, templates, consentimento e eventos do sistema. |
| Sistemas | `notifications`, `message_templates`, `ConsentRecord`, SMTP, Meta Cloud API, logs. |
| Compartilhamentos | SMTP e Meta quando ativados; transferência internacional não ocorre na infraestrutura local, mas depende dos países desses serviços. |
| Retenção | Mensagens enviadas podem ter destinatário, corpo e erro removidos após prazo aprovado; pendências manuais/falhas e provedores exigem tratamento separado. Chave de idempotência e metadados mínimos permanecem. |
| Segurança | Templates controlados, tokens não logados, status/permissões e criptografia de destinatário, payload e erro no banco desde `0052`; mensagens antigas são convertidas pela migration. Backups anteriores podem conter texto em claro. |
| Alto risco | Não por padrão; revisar conteúdo e escala. |
| Owner | Operação/comunicação + encarregado. |

### A007 — Financeiro, caixa, vendas e pagamentos

| Campo | Valor |
|---|---|
| Slug | `a007-financial-operations` |
| Finalidade | Registrar vendas, contas, caixa, cobranças, pagamentos, comissões e faturamento. |
| Base legal | Pendente no L3 — contrato, obrigação legal e proteção do crédito conforme atividade. |
| Titulares | Clientes, responsáveis financeiros, funcionários, fornecedores e sócios. |
| Dados | Nome/identificador, descrição, valores, vencimentos, status, método de pagamento, dados de cobrança e gateway. |
| Fonte | Usuários, OS, clientes, fornecedores, Asaas e webhooks. |
| Sistemas | `transacoes`, `caixa_*`, `billing_events`, `organization_subscriptions`, Asaas, logs. |
| Compartilhamentos | Asaas, contabilidade, SMTP e servidor local brasileiro; DPA/localização de serviços externos pendentes. |
| Retenção | Parte sujeita a obrigação fiscal/contratual; prazo formal ainda não definido. |
| Segurança | RBAC financeiro, tenant isolation, logs resumidos e tokens de webhook. |
| Alto risco | Não identificado; avaliar escala e fraude/decisão automatizada. |
| Owner | Financeiro + jurídico/encarregado. |

### A008 — Funcionários, permissões e auditoria administrativa

| Campo | Valor |
|---|---|
| Slug | `a008-workforce-governance` |
| Finalidade | Administrar equipe, permissões, suporte global, segurança e responsabilização. |
| Base legal | Pendente no L3 — contrato, legítimo interesse, obrigação legal e segurança. |
| Titulares | Funcionários, administradores, super admins e usuários de suporte. |
| Dados | Nome, e-mail, perfil, permissões, eventos, IP/user-agent se coletados, ações e timestamps. |
| Fonte | Usuário, administrador, autenticação e sistema. |
| Sistemas | `usuarios`, `user_sessions`, `eventos_log`, `platform_settings`, logs operacionais. |
| Compartilhamentos | Equipe interna estritamente autorizada, servidor local e Sentry somente se habilitado. |
| Retenção | Auditoria e sessões não têm matriz de prazo aprovada; incidentes devem manter registros por 5 anos quando aplicável. |
| Segurança | RBAC/ABAC, super admin separado, 2FA, revogação e logs. |
| Alto risco | Não por padrão; acesso global privilegiado exige RIPD/controles se houver monitoramento extensivo. |
| Owner | Segurança/plataforma + encarregado. |

### A009 — Direitos do titular, consentimento e privacidade

| Campo | Valor |
|---|---|
| Slug | `a009-data-subject-rights` |
| Finalidade | Registrar consentimentos, responder solicitações, exportar e anonimizar dados. |
| Base legal | Pendente no L3; obrigação legal para atendimento e consentimento somente quando a finalidade exigir. |
| Titulares | Clientes e solicitantes autenticados/representados. |
| Dados | Identificador do titular, tipo/status da solicitação, finalidade, concessão/revogação, datas e observações. |
| Fonte | Titular, representante e administrador autorizado. |
| Sistemas | `consent_records`, `data_subject_requests`, `retention_policies`, exportações ZIP e logs. |
| Compartilhamentos | Titular, encarregado e assistência controladora; operadores conforme caso. |
| Retenção | Solicitações e consentimentos não têm retenção formal aprovada. |
| Segurança | Controle por tenant, trilha resumida, validação de titular e exportação protegida; workflow incompleto. |
| Alto risco | Não por si; depende de escala e conteúdo. |
| Owner | Encarregado/jurídico + engenharia. |

### A010 — Site publicado, domínios e conteúdo empresarial

| Campo | Valor |
|---|---|
| Slug | `a010-tenant-sites` |
| Finalidade | Hospedar site, configurar domínio/subdomínio, publicar conteúdo e receber contatos públicos. |
| Base legal | Pendente no L3; separar dados de visitantes, leads e dados empresariais. |
| Titulares | Donos/administradores, visitantes, leads e clientes mencionados no conteúdo. Menores: acesso provável precisa ser decidido. |
| Dados | Domínios, contatos, arquivos enviados, logs de acesso e eventual formulário do site. |
| Fonte | Empresa, visitante e DNS/provedor. |
| Sistemas | `tenant_sites`, `tenant_site_bundles`, storage local/S3, Cloudflare/DNS, logs web. |
| Compartilhamentos | Servidor local brasileiro; Cloudflare, S3 e observabilidade somente se habilitados. |
| Retenção | Bundles, logs e contatos sem prazo aprovado. |
| Segurança | Validação de ZIP, isolamento por tenant, domínio verificado e storage keys. |
| Alto risco | Pendente se houver profiling, menores ou formulários de alto volume. |
| Owner | Plataforma/infra + assistência. |

### A011 — Importação de dados externos

| Campo | Valor |
|---|---|
| Slug | `a011-data-import` |
| Finalidade | Migrar clientes, produtos, OS e financeiro de sistemas anteriores. |
| Base legal | Pendente no L3; deve preservar a finalidade original e a responsabilidade do controlador. |
| Titulares | Todos os titulares contidos no banco/arquivo de origem. |
| Dados | Potencialmente todas as categorias do sistema; inclui CPF/CNPJ, contatos, OS, laudos e financeiro. |
| Fonte | Firebird, MySQL/MariaDB, SQLite, CSV, XLSX e ZIP enviados pelo super admin. |
| Sistemas | Serviço de importação, `instance/import_uploads`, logs de importação e tabelas de destino. |
| Compartilhamentos | Nenhum terceiro necessário por padrão; servidor local brasileiro recebe o arquivo temporário. |
| Retenção | Upload temporário precisa de expiração/limpeza formal; registros importados seguem atividades de destino. |
| Segurança | Exclusivo do super admin, prévia, mapeamento, duplicidade e confirmação; senha não deve ser persistida. |
| Alto risco | **Possível** pela abrangência e escala; avaliar RIPD e controles de arquivo. |
| Owner | Plataforma/engenharia + encarregado. |

### A012 — Backups, observabilidade e resposta operacional

| Campo | Valor |
|---|---|
| Slug | `a012-backup-observability` |
| Finalidade | Recuperar o serviço, detectar falhas, investigar incidentes e manter disponibilidade. |
| Base legal | Pendente no L3 — segurança, obrigação legal e legítimo interesse conforme contexto. |
| Titulares | Todos os titulares presentes no banco, arquivos e logs. |
| Dados | Cópias integrais, identificadores de sessão, IP/user-agent, erros e metadados operacionais. |
| Fonte | Banco, storage, aplicação e infraestrutura. |
| Sistemas | Backups MariaDB/storage, arquivos criptografados, Sentry opcional, métricas e logs. |
| Compartilhamentos | Servidor local brasileiro; Sentry/storage externo somente se habilitados. Transferência internacional depende dessas ativações. |
| Retenção | Backups têm recomendação operacional, mas não matriz LGPD por categoria nem descarte verificável. |
| Segurança | Scripts de criptografia, restore, permissões e documentação; chave/destino real pendentes. |
| Alto risco | Sim para cópias integrais/alta escala; RIPD e controles de acesso devem ser avaliados. |
| Owner | Infra/SRE + segurança/encarregado. |

## Pendências que bloqueiam o ROPA

1. Confirmar controlador/operador em cada contrato entre Zokyo e assistências.
2. Confirmar provedores, regiões, suboperadores e transferências internacionais.
3. Confirmar público, volume de titulares, faturamento e existência de menores.
4. Definir prazos de retenção com jurídico/contábil/operacional.
5. Vincular cada atividade a uma base legal aprovada no L3.

## Checklist de qualidade

- [x] Modelos, rotas, integrações e logs principais revisados.
- [x] Dados comuns e possíveis dados sensíveis identificados.
- [x] Menores marcados como decisão pendente onde o público pode alcançá-los.
- [ ] Bases legais explícitas — próximo L3.
- [ ] Retenção aprovada por atividade — L5.
- [ ] Operadores, DPAs e transferências — L4.
- [ ] ROPA consolidado — etapa posterior ao L3/L4.
