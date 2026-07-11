# Modulo de laudos tecnicos

O modulo de laudos cria documentos tecnicos vinculados a uma ordem de servico existente. O fluxo atual cobre:

- listagem paginada em `/laudos`;
- criacao por OS em `/laudos/novo?os_id=<id>`;
- preenchimento inicial a partir da OS, cliente e equipamento;
- rascunho editavel salvo no banco;
- fotografias privadas em `instance/uploads/reports/<organization>/<uuid>/photos`;
- finalizacao imutavel com numero `LAU-AAAA-000001`;
- snapshot de empresa, cliente, equipamento e tecnico;
- PDF A4 gerado no servidor com ReportLab;
- hash SHA-256 e metadados salvos no banco;
- download autenticado do PDF;
- duplicacao, revisao formal e cancelamento auditado;
- historico de eventos por laudo;
- verificacao publica minima por token, sem dados sensiveis.

## Migracao

Enquanto o projeto ainda nao usa Flask-Migrate/Alembic, aplique:

```bash
python scripts/migrate_laudos.py
```

O script e idempotente e cria:

- `laudo_counters`;
- `laudos_tecnicos`;
- `laudo_fotos`;
- `laudo_eventos`;
- indices de busca por OS, cliente, status, emissao, fotos e eventos.

## Variaveis

```env
REPORTS_UPLOAD_FOLDER=
REPORTS_PUBLIC_VERIFICATION=true
```

Se `REPORTS_UPLOAD_FOLDER` ficar vazio, os arquivos ficam em `instance/uploads/reports`.

## Regras principais

- somente rascunhos podem ser editados;
- laudos finalizados nao sao alterados silenciosamente;
- revisoes criam novo rascunho vinculado ao laudo origem;
- PDFs e fotos nao ficam em `static/`;
- fotos aceitas: JPEG, PNG e WebP, validadas por Pillow;
- as cinco categorias padrao sao obrigatorias para finalizar.

## Limitacoes conhecidas

- ainda nao existe tenant real alem de `organization_id=1`;
- permissao esta baseada nos perfis existentes (`admin`, `operacional`, `consulta`, `cadastro`);
- a migracao formal via Alembic ainda precisa ser implantada no projeto;
- QR Code visual ainda nao foi adicionado ao PDF, mas o token de verificacao ja existe;
- thumbnails dedicados ainda nao foram separados do arquivo otimizado.
