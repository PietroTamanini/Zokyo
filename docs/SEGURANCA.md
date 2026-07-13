# Seguranca

## Implementado

- CSRF global para metodos mutantes.
- CSP com nonce para scripts inline.
- Headers de seguranca em `after_request`.
- HSTS em producao.
- Timeout absoluto e por inatividade de sessao.
- Revalidacao de usuario ativo por request.
- Rate limiting de login.
- Criptografia de segredos de configuracao via Fernet.
- Upload privado para OS e laudos.
- Validacao real de imagens de laudos via Pillow.
- Erros HTML/API sem stack trace.
- Recuperacao de senha com token aleatorio, hash persistido, expiracao, uso unico, anti-enumeracao e rate limit.
- CSP sem CDN para scripts, estilos e fontes; scripts inline exigem nonce por request.
- Request ID em respostas e logs JSON de producao com mascaramento de dados sensiveis.
- 2FA TOTP para administradores com segredo criptografado, confirmacao antes da ativacao e codigos de recuperacao de uso unico armazenados como hash.
- RBAC aplicado no backend das rotas HTML e JSON, com testes negativos por perfil.
- Isolamento de tenant tambem validado nas chaves estrangeiras recebidas nas APIs.
- `detect-secrets`, Bandit e `pip-audit` executados na CI.

## Laudos

- PDFs e fotos ficam fora de `static/`.
- Laudo finalizado e imutavel.
- Revisoes criam novo documento.
- PDF possui SHA-256 e codigo de verificacao.
- Verificacao publica pode ser desativada por `REPORTS_PUBLIC_VERIFICATION=false`.

## Limitacao externa

Antivirus de arquivos pode ser integrado quando houver um servico de varredura definido pela infraestrutura. Mesmo sem ele, uploads sao limitados, decodificados e regravados como imagem valida, sem SVG, HTML ou executaveis.
# Retencao segura

As politicas em `/privacidade/retencao` ficam inativas por padrao e exigem confirmacao administrativa. A rotina automatica alcanca apenas tokens antigos e notificacoes terminais; nunca remove OS, laudos, clientes, financeiro ou logs. Os prazos devem ser aprovados pelo controlador/juridico antes da ativacao.
