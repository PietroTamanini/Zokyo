# LIA — A006 Comunicações operacionais

**Status:** rascunho para aprovação  
**Base avaliada:** LGPD, Art. 7º, IX, somente para comunicações não essenciais; comunicações contratuais devem preferir Art. 7º, V.

## Condições

Separar mensagens de status de OS/cobrança de marketing. Para marketing, informar finalidade, oferecer opt-out simples e não reutilizar consentimento de atendimento.

## Necessidade e balanceamento

Enviar somente destinatário, conteúdo e identificador necessários. Não incluir CPF completo, documentos, tokens ou detalhes excessivos de OS em mensagens. Expectativa é média para atualizações de atendimento e baixa para marketing sem opt-in/aviso.

## Salvaguardas

- Templates aprovados e versionados.
- Opt-out por canal.
- Logs sem conteúdo livre e sem token bruto.
- DPAs e localização dos provedores SMTP/Meta.

**Decisão:** pendente de jurídico/encarregado e inventário de operadores.
