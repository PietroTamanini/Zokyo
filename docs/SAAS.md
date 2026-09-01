# Preparacao SaaS

Estado revisado em 2026-09-01: multiempresa, trial automático, planos, quotas, isolamento, sandbox e adapter de assinatura recorrente Asaas estão implementados. Preços, impostos, credenciais, licença, contratos e homologação comercial continuam externos.

## Estado atual

O Zokyo ja possui base SaaS operacional:

- `Organization` como tenant central;
- `organization_id` obrigatorio nos modelos de negocio;
- escopo ORM central em `app/utils/tenancy.py`;
- provisionamento via `create-organization`;
- planos globais idempotentes via `seed-system`;
- limites de escrita por assinatura;
- painel global da plataforma;
- webhooks sandbox e Asaas com autenticação e idempotência;
- criação/reuso de cliente, assinatura recorrente e cancelamento no Asaas;
- trial automático e bloqueio de escrita após expiração/inadimplência;
- quotas de usuários, clientes, OS abertas e armazenamento;
- Redis para sessões e rate limit distribuído, com fallback seguro;
- storage S3 compatível opcional para arquivos privados;
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

O código do provider Asaas está disponível, mas preços, credenciais, conta homologada, moeda, impostos e política jurídica dependem do proprietário e/ou assessoria jurídica. O sandbox deve ser usado antes da ativação real.

Consulte `docs/DECISOES_EXTERNAS.md`.
