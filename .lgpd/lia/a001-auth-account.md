# LIA — A001 Conta, autenticação e segurança

**Status:** rascunho para aprovação  
**Base avaliada:** LGPD, Art. 7º, IX; segurança com dado sensível deve observar também Art. 11, II, g.

## Finalidade

Proteger contas, sessões, recuperação de acesso e o ambiente multiempresa contra fraude e acesso indevido.

## Necessidade

Nome, e-mail, identificador de sessão, timestamps e eventos mínimos são necessários. Reduzir IP/user-agent ao mínimo necessário para prevenção e investigação; não registrar senha, token bruto ou código.

## Balanceamento

- Expectativa: alta para autenticação e segurança.
- Impacto: moderado se logs forem excessivos; baixo com minimização e acesso restrito.
- Salvaguardas: hash de senha, TOTP, revogação, RBAC/ABAC, rate limit e criptografia.
- Oposição: a oposição não pode desativar controles essenciais de segurança, mas o titular deve receber transparência e exercer os direitos aplicáveis.

## Condições antes de aprovar

- Definir retenção de sessões, logs e incidentes.
- Formalizar acesso do super admin e revisão periódica.
- Confirmar provedores e transferências internacionais.

**Decisão:** pendente de encarregado/jurídico.
