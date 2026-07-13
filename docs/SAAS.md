# Preparacao SaaS

## Estado atual

O sistema possui isolamento multiempresa incremental: `Organization`, tenant obrigatorio nos modelos de negocio, escopo ORM central e provisionamento por CLI. O painel global comercial, planos e cobranca permanecem fora do painel comum.

## Caminho incremental

1. Manter testes de isolamento horizontal em toda nova rota.
2. Criar painel global separado do painel das organizacoes.
3. Modelar planos e limites apos decisao comercial.
4. Implementar provider fake/sandbox antes de selecionar gateway real.

## Comercial

Ainda nao implementado:

- planos;
- assinaturas;
- limites;
- cobranca;
- webhooks;
- inadimplencia;
- gateway fake/sandbox;
- auditoria de cobranca.

Nenhum gateway real deve ser escolhido sem decisao do proprietario.

## LGPD

Pendencias:

- retencao por tipo de dado;
- exportacao de dados;
- anonimizacao/exclusao quando legalmente possivel;
- registro de consentimento;
- politica de acesso a documentos e fotografias.
# Isolamento incremental

A entidade `Organization` e as migracoes `20260712_0006`/`0007` criam uma organizacao padrao e fazem backfill de todos os modelos de negocio. O escopo em `app/utils/tenancy.py` adiciona filtro central a consultas ORM e atribui o tenant do usuario a novos registros.

O escopo inclui clientes, OS, estoque, fornecedores, financeiro, configuracoes, auditoria, coletas, fotos, historicos, defeitos e laudos. Rotas de laudos, fotos e usuarios tambem possuem filtros explicitos para defesa em profundidade. Tokens de verificacao publica continuam independentes de IDs sequenciais e exibem apenas os campos publicos documentados.

Operacoes globais futuras devem usar `execution_options(include_all_tenants=True)` somente em comandos administrativos fora do painel comum e com auditoria. O navegador nunca escolhe `organization_id`.

## Provisionamento

Novas organizacoes sao criadas fora do painel comum, com senha solicitada de forma oculta pelo Click:

```bash
python -m flask --app wsgi:app create-organization \
  --name "Empresa Exemplo" \
  --slug empresa-exemplo \
  --admin-name "Administrador" \
  --admin-email admin@example.com
```

O comando valida slug, e-mail e senha forte, cria configuracao isolada, administrador vinculado e evento de auditoria na mesma transacao.
