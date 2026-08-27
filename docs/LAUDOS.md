# Modulo de laudos tecnicos

Estado revisado em 2026-08-27: criação, rascunho, templates, PDF, storage privado e concorrência possuem cobertura automatizada e auditoria visual responsiva. A identidade final do PDF e eventual validade jurídica dependem de homologação externa.

O modulo de laudos cria documentos tecnicos vinculados a uma ordem de servico existente. O fluxo atual cobre:

- listagem paginada em `/laudos`;
- criacao por OS em `/laudos/novo?os_id=<id>`;
- preenchimento inicial a partir da OS, cliente e equipamento;
- rascunho editavel salvo no banco;
- fotografias privadas em `instance/uploads/reports/<organization>/<uuid>/photos`;
- thumbnails privados, sem metadados EXIF, e reordenacao auditada;
- finalizacao imutavel com numero `LAU-AAAA-000001`;
- snapshot de empresa, cliente, equipamento e tecnico;
- PDF A4 gerado no servidor com ReportLab;
- hash SHA-256 e metadados salvos no banco;
- download autenticado do PDF;
- duplicacao, revisao formal e cancelamento auditado;
- comprovante PDF separado para documentos cancelados, preservando o PDF original;
- exportacao CSV filtrada, isolada por empresa e protegida contra formulas de planilha;
- historico de eventos por laudo;
- QR Code e verificacao publica minima por token, sem dados sensiveis.

## Migracao

O projeto usa Flask-Migrate/Alembic. Em uma instalacao ja existente, faca backup e aplique:

```bash
python -m flask --app wsgi:app db upgrade
```

As revisoes `20260711_0001` e `20260712_0002` criam:

- `laudo_counters`;
- `laudos_tecnicos`;
- `laudo_fotos`;
- `laudo_eventos`;
- coluna privada de thumbnail;
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

## Decisoes futuras

- uma API JSON dedicada para laudos so deve ser criada quando houver consumidor externo definido;
- assinatura com validade juridica especifica depende da politica do proprietario e/ou assessoria juridica;
- armazenamento compativel com S3 pode ser adicionado se o ambiente de producao exigir.

## Auditoria do storage

Liste arquivos sem referencia no banco:

```bash
python -m flask --app wsgi:app laudos storage-audit
```

Depois de revisar a lista, remova-os explicitamente com `--delete`. O comando ignora arquivos temporarios em uso.
