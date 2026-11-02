# Fechamento de caixa — Zokyo (Etapa 11)

## Objetivo

Controlar o fechamento diario de caixa das assistencias: abertura, movimentacoes,
conferencia de valores e diferenca, com integracao ao modulo financeiro existente.

## Modelo

- `caixas_sessoes`: uma sessao por tenant por turno (status `aberto`/`fechado`).
- `caixa_movimentos`: movimentacoes da sessao (`entrada`, `saida`, `sangria`, `suprimento`).

Migração: `migrations/versions/20260928_0032_add_cash_closure.py`.

## Regras de negocio

- Cada tenant possui no maximo uma sessao de caixa aberta simultaneamente.
- O valor esperado no fechamento e `saldo_inicial + entradas - saidas - sangrias + suprimentos`.
- A diferenca e `valor_conferido - valor_fechado_esperado` (positivo = sobra).
- Fechamento duplicado da mesma sessao e rejeitado (`409`).
- Movimentacoes exigem sessao aberta; valores devem ser positivos e dentro do limite.

## API

Base: `/api/cash`

- `GET /api/cash/sessoes` — historico de fechamentos (filtros: `limit`).
- `POST /api/cash/sessoes/abrir` — abre caixa (`saldo_inicial`).
- `GET /api/cash/sessoes/<sessao_id>` — detalhe da sessao.
- `POST /api/cash/sessoes/<sessao_id>/fechar` — fecha com `valor_conferido`.
- `GET /api/cash/movimentos?sessao_id=<id>` — movimentacoes da sessao.
- `POST /api/cash/movimentos` — registra movimentacao (`tipo`, `valor`).
- `GET /api/cash/relatorio` — resumo (`sessao_id` opcional).

Permissoes: `caixa.view` (leitura) e `caixa.manage` (escrita). Perfis `admin` e `financeiro`.

## Integracao com modulo financeiro

- Movimentacoes alimentam o fechamento de caixa; lancamentos financeiros
  continuam registrados em `/api/transacoes` (receita/despesa/conciliacao).
- Nao ha duplicacao: fechamento nao cria transacoes automaticamente.

## Testes

- `tests/test_cash_closure.py` — servico, API, isolamento e permissoes.

## Seguranca

- Todas as rotas exigem autenticacao via sessao/Bearer.
- Escopo por tenant respeitado via `g.organization_id`.
- Eventos de abertura/movimentacao/fechamento registrados em `eventos_log` (modulo `financeiro`).
