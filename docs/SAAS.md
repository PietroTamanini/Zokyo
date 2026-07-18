# Preparacao SaaS

## Estado atual

O Zokyo ja possui base SaaS operacional:

- `Organization` como tenant central;
- `organization_id` obrigatorio nos modelos de negocio;
- escopo ORM central em `app/utils/tenancy.py`;
- provisionamento via `create-organization`;
- planos globais idempotentes via `seed-system`;
- limites de escrita por assinatura;
- painel global da plataforma;
- webhook sandbox de cobranca;
- convites de usuario com token em hash, uso unico e expiracao;
- identidade visual por empresa;
- controles LGPD de consentimento, exportacao, anonimizacao e retencao.

Operacoes globais devem usar `execution_options(include_all_tenants=True)` somente em comandos administrativos ou servicos internos auditados. O navegador nunca escolhe `organization_id`.

## Provisionamento

Crie organizacoes pelo CLI:

```bash
python -m flask --app wsgi:app create-organization \
  --name "Empresa Exemplo" \
  --slug empresa-exemplo \
  --admin-name "Administrador" \
  --admin-email admin@example.com
```

Depois das migracoes, mantenha os planos globais atualizados:

```bash
python -m flask --app wsgi:app seed-system
```

## Decisoes externas

O provider real de cobranca, precos, gateway, moeda, impostos e politica juridica de assinatura dependem do proprietario e/ou assessoria juridica. O sandbox existe para validar o fluxo tecnico sem assumir contrato comercial.

Consulte `docs/DECISOES_EXTERNAS.md`.
