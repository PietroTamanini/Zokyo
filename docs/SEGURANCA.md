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

## Laudos

- PDFs e fotos ficam fora de `static/`.
- Laudo finalizado e imutavel.
- Revisoes criam novo documento.
- PDF possui SHA-256 e codigo de verificacao.
- Verificacao publica pode ser desativada por `REPORTS_PUBLIC_VERIFICATION=false`.

## Pendencias

- RBAC atomico persistido.
- 2FA para administradores.
- Recuperacao de senha com token de uso unico.
- CSP de producao sem CDN e com menos `unsafe-inline` em estilos.
- Secret scanning robusto no CI.
- Antivirus opcional para uploads.
- Request ID e logs estruturados.
- Testes amplos de acesso indevido e vazamento multiempresa.
