# Bases Legais por Atividade de Tratamento

**Última atualização:** 2026-11-06  
**Status:** proposta técnica para revisão do controlador, jurídico e encarregado  
**Escopo:** atividades A001–A012 de `.lgpd/data-map.md`.

> Esta matriz não substitui decisão jurídica. A base deve ser confirmada por finalidade, contrato e papel de cada parte. Consentimento não é base universal e não deve ser usado para tornar finalidades essenciais e não essenciais inseparáveis (LGPD, Arts. 7º e 9º, § 2º).

## Matriz resumida

| Atividade | Base proposta para dados comuns | Dados sensíveis | Consentimento | Retenção | LIA/RIPD |
|---|---|---|---|---|---|
| A001 Conta e autenticação | Art. 7º, V (contrato) e IX (segurança, com LIA) | Art. 11, II, g se autenticação/segurança envolver dado sensível | Não para acesso essencial; sim para finalidade opcional | Definir por conta, sessão e obrigação | LIA `a001-auth-account` |
| A002 Tenant e billing | Art. 7º, V; Art. 7º, II quando houver obrigação legal; Art. 7º, X quando proteção de crédito for realmente aplicável | Não esperado | Não para contrato/cobrança | Fiscal/contratual a validar | Não por padrão |
| A003 Clientes | Art. 7º, V; Art. 7º, IX somente após LIA para usos não essenciais | Não por padrão | Marketing separado: Art. 7º, I ou IX + opt-out | Definir por contrato/obrigação | LIA se uso secundário |
| A004 OS/laudos/evidências | Art. 7º, V e VI para defesa de direitos; Art. 7º, II quando aplicável | Art. 11, II, d/f conforme conteúdo e finalidade; não usar Art. 7º, V para sensíveis | Art. 11, I somente para finalidade sensível opcional e específica | Definir com jurídico/contábil | RIPD provável; LIA não substitui RIPD |
| A005 Portal/consulta | Art. 7º, V e IX para segurança/abuso com LIA | Art. 11 conforme dado exposto | Não para funcionalidade contratual essencial | Tokens curtos; conteúdo conforme A003/A004 | Avaliar RIPD por exposição |
| A006 Comunicações | Contratuais: Art. 7º, V; marketing: Art. 7º, I ou IX + opt-out | Art. 11 conforme conteúdo | Obrigatório para marketing se escolhido | Definir por canal e finalidade | LIA `a006-communications` para LI |
| A007 Financeiro | Art. 7º, V, II e VI conforme transação/obrigação | Não esperado; avaliar comprovantes | Não para obrigação/contrato; opcional separado | Definir com contábil/jurídico | Não por padrão |
| A008 Equipe/auditoria | Art. 7º, V, II e IX + LIA para monitoramento | Art. 11, II, g somente quando necessário para segurança/autenticação | Não para segurança essencial | Definir por segurança, emprego e incidente | LIA `a008-workforce-governance` |
| A009 Direitos/consentimentos | Art. 7º, II e VI para atender obrigação/direito do titular | Art. 11 conforme dado solicitado | Consentimento registrado somente quando a finalidade exigir | Manter prova pelo prazo necessário | RIPD não por si |
| A010 Site/domínios | Art. 7º, V para serviço contratado; IX + LIA para logs/abuso | Não esperado | Formulários/marketing separados | Definir logs, bundles e leads | LIA `a010-tenant-sites` se analytics |
| A011 Importação | Art. 7º, V/II/VI conforme finalidade de origem/destino | Preservar base Art. 11 da origem; não ampliar finalidade | Não coletar novo consentimento automaticamente; avaliar compatibilidade | Arquivo temporário curto; destino conforme atividade | RIPD possível por escala |
| A012 Backups/observabilidade | Art. 7º, IX + LIA e Art. 7º, II quando aplicável | Art. 11, II, g quando indispensável à segurança | Não para segurança essencial | Backup e logs com prazos formalizados | RIPD se larga escala |

## Regras de decisão obrigatórias

1. Separar atendimento contratual de marketing; consentimento deve ser específico, destacado, livre e revogável (Arts. 7º, I, 8º e 9º).
2. Não usar execução de contrato ou legítimo interesse como base para dado sensível. Para A004, classificar o conteúdo real e aplicar Art. 11.
3. Para legítimo interesse, concluir a LIA antes de ativar a finalidade, com transparência, necessidade, balanceamento e oposição fácil (Art. 10).
4. Para crianças, usar consentimento específico e destacado de responsável quando aplicável (Art. 14, § 1º) e avaliar a Lei 15.211/2025.
5. Toda finalidade nova, compartilhamento novo ou mudança de prazo exige revisão do aviso de privacidade (Art. 9º, § 2º).

## Decisões pendentes do controlador

- Definir se Zokyo atua como controlador, operador ou ambos em cada atividade.
- Confirmar se o produto é acessado por menores ou é de acesso provável.
- Confirmar quais integrações recebem dados e em quais países.
- Confirmar contratos, obrigações fiscais e prazos de defesa.
- Aprovar ou rejeitar cada LIA e decidir quais atividades exigem RIPD (Art. 38).

## Próximo passo

Consolidar operadores, DPAs e transferências em `.lgpd/vendors/` e `.lgpd/transfers/` no L4.
