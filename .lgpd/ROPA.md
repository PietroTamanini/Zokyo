# Registro de Operações de Tratamento — ROPA técnico

**Versão:** v0.1 — rascunho técnico  
**Data:** 06/11/2026  
**Aprovação:** pendente do responsável de cada assistência, Zokyo e revisão jurídica

> Este registro foi derivado do mapa técnico em `.lgpd/data-map.md`. Ele não substitui a validação das finalidades, bases legais, prazos, contratos e papéis de cada assistência.

| ID | Operação | Controlador principal | Operador/apoio | Titulares | Dados | Finalidade | Base legal proposta | Retenção |
|---|---|---|---|---|---|---|---|---|
| A001 | Conta e autenticação | Zokyo para contas do SaaS; assistência para seus usuários | Zokyo/infra local | Administradores e funcionários | Identificação, e-mail, credenciais protegidas, sessões, IP técnico | Acesso e segurança | Art. 7º, V e IX/LIA conforme finalidade | Definir por categoria |
| A002 | Empresa, assinatura e cobrança | Zokyo | Gateway e infraestrutura, se ativados | Responsáveis e contatos empresariais | CNPJ, contatos, plano, eventos de cobrança | Contratação, cobrança e obrigações | Art. 7º, V, II e X conforme fluxo | Fiscal/contratual a validar |
| A003 | Clientes e atendimento | Assistência | Zokyo | Clientes e contatos | Identificação, contato, endereço e histórico | Prestação de assistência técnica | Art. 7º, V, II ou IX conforme caso | Assistência deve aprovar |
| A004 | OS, laudos e evidências | Assistência | Zokyo/infra e storage, se ativado | Clientes, técnicos e terceiros retratados | Defeito, diagnóstico, documentos, fotos e assinatura | Execução e prova do atendimento | Art. 7º, V/VI/II; Art. 11 se sensível | Legal/contratual a validar |
| A005 | Portal do cliente | Assistência | Zokyo | Clientes e contatos | Token, OS, documentos e dados exibidos | Acompanhar atendimento | Art. 7º, V/IX conforme desenho | Definir por fluxo |
| A006 | Comunicações | Assistência ou Zokyo conforme mensagem | SMTP/Meta, se ativados | Clientes, usuários e contatos | Nome, telefone, e-mail e contexto | Avisos operacionais e suporte | Art. 7º, V; marketing separado | Definir por canal |
| A007 | Financeiro | Assistência para operação; Zokyo para assinatura | Gateway, contabilidade, se ativados | Clientes e responsáveis financeiros | Valores, cobranças e documentos | Gestão financeira e obrigações | Art. 7º, II, V e VI | Fiscal/contratual a validar |
| A008 | Workforce, permissões e auditoria | Assistência; Zokyo para plataforma | Zokyo | Usuários e administradores | Perfil, ações, logs e segurança | Governança e segurança | Art. 7º, V, IX/LIA e II | Definir com segurança |
| A009 | Direitos, consentimento e privacidade | Controlador correspondente | Zokyo como apoio | Titulares | Solicitações e decisões de consentimento | Atender direitos e prestar contas | Art. 7º, II, VI ou I quando consentimento | Legal a validar |
| A010 | Sites e domínios | Assistência | Zokyo, DNS/storage se ativados | Visitantes, contatos e usuários | Conteúdo publicado, domínio e logs técnicos | Publicação e operação do site | Art. 7º, V/IX+LIA | Definir por site |
| A011 | Importação | Assistência | Zokyo | Titulares presentes na origem | Dados importados e metadados | Migração autorizada | Art. 7º, V/II/VI | Apagar temporários após processo |
| A012 | Backups e observabilidade | Controlador da operação correspondente | Zokyo/infra e Sentry, se ativado | Titulares nos sistemas | Cópias, erros e metadados técnicos | Continuidade e segurança | Art. 7º, IX/LIA e II | Definir e testar descarte |

## Governança mínima

- Cada assistência deve confirmar finalidade, base legal, categorias, prazos e canal para seus titulares.
- A Zokyo deve manter contratos de operador, instruções, suboperadores, segurança e incidentes.
- Dados sensíveis em laudos, fotos ou texto livre exigem classificação específica, minimização e avaliação de impacto.
- Fluxos acessíveis por menores devem seguir `.lgpd/eca-digital.md` e a avaliação de impacto aplicável.
- Alterações materiais exigem nova versão deste ROPA e revisão da política de privacidade.
