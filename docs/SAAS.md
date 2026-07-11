# Preparacao SaaS

## Estado atual

O sistema ainda opera como mono-tenant. O modulo de laudos ja possui `organization_id` com valor padrao `1` para preparar a migracao.

## Caminho incremental

1. Criar tabela `organizacoes`.
2. Adicionar `organization_id` a usuarios, clientes, OS, estoque, financeiro e configuracoes.
3. Criar organizacao padrao e backfill dos dados existentes.
4. Resolver tenant atual a partir da sessao do usuario.
5. Centralizar filtros por tenant em helpers/servicos.
6. Bloquear qualquer `organization_id` vindo do navegador sem validacao.
7. Criar testes de vazamento horizontal.
8. Separar painel global de administracao.

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
