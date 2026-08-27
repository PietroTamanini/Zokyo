# Checklist de go-live

Use este checklist em staging e novamente antes de liberar produção. Registre responsável, data e evidência para cada item; não marque por suposição.

## Aprovação do produto

- [ ] Fluxo de OS homologado por atendente, técnico e proprietário.
- [ ] Ciclo de orçamento, aprovação, pagamento parcial, entrega e garantia concluído.
- [ ] PDFs conferidos em tela e impressora real.
- [ ] Estoque inicial contado e conciliado.
- [ ] Português, identidade visual e contatos revisados.
- [ ] Termos, privacidade, retenção e assinatura aprovados pelo responsável jurídico.

## Ambiente e segurança

- [ ] Domínio e DNS apontam para o host correto.
- [ ] HTTPS válido, redirecionamento HTTP e HSTS confirmados.
- [ ] Segredos foram gerados fora do repositório e armazenados em cofre/secret manager.
- [ ] `FLASK_ENV=production` e `REQUIRE_ADMIN_2FA=true` estão ativos.
- [ ] Todos os administradores configuraram TOTP e guardaram códigos de recuperação.
- [ ] Banco não está exposto publicamente.
- [ ] Firewall, SSH, atualizações do host e acesso administrativo foram revisados.
- [ ] `production-check --strict-integrations` passou sem erros.

## Dados e recuperação

- [ ] Migrations executadas e `flask --app wsgi:app db check` sem divergência.
- [ ] Backup de banco e uploads executado, criptografado e enviado para destino externo.
- [ ] Restore completo realizado em ambiente descartável.
- [ ] RPO/RTO e responsáveis confirmados conforme [recuperação de desastre](DISASTER_RECOVERY.md).
- [ ] Alertas de backup falho e vencido testados.

## Integrações

- [ ] SMTP enviou recuperação de senha real para endereço controlado.
- [ ] Canal operacional recebeu alerta de teste.
- [ ] WhatsApp oficial entregou mensagem de homologação ou o uso somente manual foi aprovado.
- [ ] `PUBLIC_BASE_URL`, links do portal e assets usam o domínio HTTPS final.
- [ ] Gateway de cobrança foi homologado, se a cobrança recorrente estiver habilitada.

## Observabilidade e desempenho

- [ ] `/healthz` e `/readyz` retornam sucesso pelo endereço público esperado.
- [ ] Métricas exigem `METRICS_TOKEN` e são coletadas pelo Prometheus.
- [ ] Dashboard e regras de alerta estão ativos.
- [ ] Logs incluem request ID e chegam ao destino operacional.
- [ ] Teste de carga no host final atende ao limite de p95 definido.
- [ ] Sentry foi testado, se configurado.

## Liberação

- [ ] Imagem imutável aprovada em staging.
- [ ] Versão/tag e changelog definidos.
- [ ] Plano e responsável de rollback confirmados.
- [ ] Janela de implantação e comunicação aos usuários definidas.
- [ ] Monitoramento reforçado nas primeiras 24 horas.
- [ ] Aprovação final registrada pelo proprietário do produto.

## Evidência mínima

Guarde a saída do production check, versão implantada, resultado das migrations, data do último backup/restore, testes das integrações e nome dos aprovadores. Não armazene senhas, tokens ou chaves nas evidências.
