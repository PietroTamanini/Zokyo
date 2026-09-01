# Evidência de prontidão — 2026-09-01

Auditoria executada localmente em Docker Desktop com a composição de produção.

## Verificado

- imagem de produção construída com Python 3.11;
- suíte Python completa: 201 testes aprovados;
- Ruff e compilação Python aprovados;
- validação JavaScript: 15 arquivos aprovados;
- MariaDB, migration, Gunicorn, scheduler e Nginx saudáveis;
- Alembic em `20260901_0013 (head)` e `db check` sem divergência;
- `production-check` básico aprovado;
- teste de carga em `/healthz`: 150 requisições, zero erros, p95 de 26,5 ms;
- probes de saúde isolados do rate limit de tráfego de usuários;
- scheduler com healthcheck próprio.

## Entregas desta revisão

- custo unitário da peça congelado no consumo da OS;
- resultado, recebimento pendente e lucro por OS;
- inadimplência por cliente/OS e vencimento mais antigo;
- resumo mensal direto para o proprietário;
- templates padrão versionados por organização;
- WhatsApp por template nos status de recepção, aprovação, reparo, pronto e entregue;
- migration portável validada em SQLite e MariaDB.
- custo de mão de obra por horas e custo-hora na OS;
- trial automático e ciclo recorrente Asaas com webhook idempotente;
- Redis para sessão e rate limiting distribuídos;
- storage privado S3 compatível e quotas por plano;
- dependências de produção congeladas em `requirements-prod.lock`.

## Dependências externas ainda obrigatórias

O ambiente local usa valores fictícios e não representa credenciais comerciais. Antes do cliente real ainda é necessário fornecer e homologar:

- domínio, DNS, certificado e host definitivo;
- secret manager e segredos definitivos;
- SMTP e remetente;
- e-mail ou webhook de alertas;
- conta e templates aprovados na Meta, ou aprovação formal do modo manual;
- provedor/região/credenciais de backup externo e teste de restore;
- gateway, planos, preços e regras fiscais;
- termos, privacidade, retenção, assinatura, SLA e responsáveis;
- piloto com atendente, técnico, proprietário e cliente.

Execute `production-check --strict-integrations` no host final. Nenhuma pendência externa deve ser considerada concluída somente com esta evidência local.
