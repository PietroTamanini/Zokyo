# Discovery LGPD — Zokyo

**Data:** 2026-11-06  
**Cenário:** C — híbrido (base legada + funcionalidades novas)  
**Escopo:** aplicação Flask multiempresa, painel do super admin, portal público, site publicado de empresas, integrações e infraestrutura declaradas no repositório.

**Fase confirmada pelo responsável em 2026-11-06:** projeto de teste para avaliar se vale continuar a ideia. A Zokyo ainda não tem razão social/CNPJ/endereço/canal institucional nem encarregado definido. Os artefatos jurídicos deste repositório são rascunhos técnicos; não representam política aprovada ou operação produtiva.

## Papéis informados pelo responsável

- Cada assistência é, em regra, **controladora** dos dados dos seus clientes, funcionários e atendimentos.
- A Zokyo é principalmente **operadora**, tratando dados conforme instruções das assistências para fornecer o sistema.
- A Zokyo também pode ser **controladora independente** dos dados necessários ao próprio SaaS: cadastro de empresas, administradores da plataforma, cobrança, segurança, suporte e cumprimento de obrigações legais.
- Se a ideia avançar, a infraestrutura principal planejada é um servidor local na residência do responsável, no Brasil. O local e os provedores efetivamente ativados ainda precisam ser confirmados antes de produção.
- O sistema pode ser acessado por menores. A avaliação do ECA Digital passa a ser aplicável de forma preventiva ao portal/site público e a qualquer fluxo acessível por adolescentes.

## Evidências encontradas

### Dados e modelos

- `Usuario`: nome, e-mail, hash de senha, TOTP criptografado, códigos de recuperação, perfil, sessões e versão de segurança.
- `Cliente`: nome, CPF/CNPJ, telefone, e-mail, CEP, endereço, número, cidade e UF. `endereco`, `numero_casa` e outros textos sensíveis usam `EncryptedText`; CPF/CNPJ/telefone/e-mail possuem índices cegos para busca.
- `OrdemServico`, `OSHistorico`, `LaudoTecnico`, fotos, assinaturas e portal: dados de atendimento, equipamento, defeito, diagnóstico, documentos e evidências de aceite.
- `Transacao`, caixa, cobrança e assinatura: dados financeiros, pagamento, faturamento e integração Asaas.
- `ConsentRecord` e `DataSubjectRequest` existem em `app/models/privacy.py`, mas o fluxo atual é predominantemente administrativo e não constitui sozinho um canal completo para titulares.
- `EventoLog`, notificações, tokens de recuperação, tokens de portal e sessões mantêm trilhas operacionais. O `EventoLog` atual não é hash-encadeado nem append-only por desenho.

### Tratamentos e interfaces

- Login de empresa e login do super admin, recuperação/redefinição de senha, convites, 2FA e sessões revogáveis.
- Cadastro e gestão de clientes, funcionários, ordens de serviço, laudos, estoque, vendas, financeiro, portal do cliente, notificações e sites publicados.
- Exportação e anonimização administrativa em `app/services/privacy.py`; a anonimização é bloqueada quando existem OS ou laudos sujeitos a retenção.
- Retenção configurável hoje cobre tokens de recuperação, tokens de portal e notificações terminais. Não há política automatizada equivalente documentada para clientes, OS, laudos, fotos, assinaturas, financeiro e logs.
- Uploads de laudos, fotos, assinaturas, sites e importações externas usam storage local ou S3 opcional. É necessário confirmar isolamento, criptografia, ciclo de vida e localização do storage em produção.

### Segurança existente

- Multi-tenancy, RBAC/ABAC, índices cegos, alguns campos criptografados, rate limit, CSRF, headers de segurança, 2FA e logs operacionais existem no código.
- Backups têm scripts de criptografia e restore documentados, mas o uso em produção, a gestão da chave, o destino externo e os testes periódicos ainda dependem de operação externa.
- A auditoria geral registra várias mutações, mas há risco de excesso de dados livres em descrições históricas e não há garantia de imutabilidade/hash chain.

### Operadores e integrações

- MariaDB, Redis e aplicação no servidor local brasileiro; SMTP, Asaas, Meta WhatsApp Cloud API, Cloudflare DNS, S3 compatível opcional, Sentry opcional e demais provedores externos ainda precisam ser confirmados.
- Não foi encontrada evidência versionada de inventário de operadores, DPAs assinados, avaliação de transferência internacional ou cláusulas-padrão brasileiras.

### Governança e transparência

- Há telas e modelos de privacidade, retenção, consentimento e solicitações, mas não foram encontrados no escopo auditado um ROPA aprovado, matriz de base legal por atividade, RIPD, designação pública do encarregado, política de privacidade versionada ou runbook formal de incidentes.
- O sistema pode ser acessado por menores. Mesmo que não seja direcionado a esse público, o portal/site público e outros fluxos acessíveis exigem avaliação preventiva da Lei 15.211/2025 (ECA Digital), com decisão de produto/jurídica e medidas proporcionais ao risco.

## Limitações da descoberta

- Código não prova configuração real de produção, contratos, localização física dos provedores, volume de titulares, faturamento ou existência de incidentes anteriores.
- A classificação final de controlador/operador por fluxo depende dos contratos entre Zokyo e cada assistência.
- Nenhuma política jurídica foi publicada ou aprovada durante esta etapa.
