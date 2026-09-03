# O que falta para concluir o Zokyo

Atualizado em 2026-09-03 após auditoria e cobertura dedicada dos indicadores financeiros por OS.

Legenda: `[x]` indica implementação existente e verificada. `[ ]` indica trabalho ainda necessário. Itens de infraestrutura, credenciais, validação humana ou decisão comercial não podem ser concluídos somente no repositório.

## Estado atual

O sistema está tecnicamente apto para um piloto controlado. Ainda não está liberado para produção comercial porque o ambiente real, os backups externos, as integrações e as políticas operacionais não foram configurados ou homologados.

- [x] Aplicação, MariaDB e site público executam em Docker com healthchecks saudáveis.
- [x] Schema atualizado até a migration `20260731_0012` e sem divergência detectada pelo Alembic.
- [x] 215 testes Python aprovados.
- [x] 200 cenários Playwright executados em compact, mobile, tablet, desktop e wide.
- [x] Auditoria de overflow, runtime, HTTP 500 e WCAG sem defeito reproduzível nas telas isoladas.
- [x] Teste local de 150 requisições simultâneas aprovado sem erro após correção do rate limit.
- [x] Ruff, compilação Python, validação JavaScript e auditorias de dependências aprovados.

## 1. Bloqueadores de produção

- [ ] Configurar o host real com `FLASK_ENV=production`.
- [ ] Armazenar `SECRET_KEY`, `ENCRYPTION_SALT`, `BLIND_INDEX_KEY`, `BACKUP_ENCRYPTION_KEY` e `METRICS_TOKEN` fortes fora do repositório.
- [ ] Configurar domínio, DNS, HTTPS e proxy reverso.
- [ ] Definir `PUBLIC_BASE_URL` ou `HEALTHCHECK_URL` com a URL HTTPS pública.
- [ ] Ativar `REQUIRE_ADMIN_2FA=true` e cadastrar o segundo fator dos administradores.
- [ ] Configurar SMTP e `MAIL_FROM`, então testar recuperação de senha real.
- [ ] Configurar `ALERT_EMAIL` ou `ALERT_WEBHOOK_URL` e confirmar o recebimento de um alerta de teste.
- [ ] Configurar WhatsApp Cloud API ou aceitar formalmente a operação apenas com fallback manual.
- [ ] Executar `flask --app wsgi:app production-check --strict-integrations` até não haver erros.
- [ ] Executar o checklist de [go-live](docs/GO_LIVE.md).

## 2. Backup e recuperação

- [x] Scripts de banco, storage privado, criptografia, manifesto, integridade e restore implementados.
- [x] Runbooks de backup e recuperação documentados.
- [ ] Escolher provedor, região, retenção e responsável pelo backup externo.
- [ ] Agendar backup diário do MariaDB e dos uploads privados.
- [ ] Criptografar e enviar cada backup para fora do host da aplicação.
- [ ] Configurar alerta para backup falho ou vencido.
- [ ] Restaurar banco e arquivos em ambiente descartável antes do primeiro cliente real.
- [ ] Registrar evidência do teste de restore e repetir mensalmente.
- [ ] Simular recuperação de desastre trimestralmente.

## 3. Fluxo de ordem de serviço

- [x] Criar, editar, aprovar, pagar parcialmente, imprimir, baixar, restaurar e consultar OS.
- [x] Impedir finalização sem pagamento integral.
- [x] Manter OS baixadas fora da lista operacional principal.
- [x] Checklist, fotos, assinatura, laudo, peças, serviços e observações internas separados.
- [x] Fluxo principal coberto por testes automatizados.
- [ ] Medir com atendente real se uma OS pode ser aberta em menos de um minuto.
- [ ] Homologar a busca de clientes com uma base grande e nomes/documentos semelhantes.
- [ ] Testar o formulário com atendente e técnico e reduzir etapas que gerarem dúvida.
- [ ] Aprovar visualmente o PDF final com a identidade da assistência e uma impressora real.
- [ ] Executar um ciclo real de orçamento, aprovação, pagamento parcial, entrega e garantia no piloto.

## 4. Financeiro

- [x] Mostrar entrada do dia, receitas, despesas, saldo, caixa, valores a receber e a pagar.
- [x] Filtrar lançamentos por período, tipo e status.
- [x] Registrar pagamentos, conciliação, descontos e comissões.
- [x] Exportar dados contábeis e gerar relatórios gerenciais.
- [x] Criar uma lista direta de OS com pagamento incompleto.
- [x] Calcular lucro por OS usando custo histórico das peças, custo de mão de obra (`horas_trabalho * custo_hora`), comissão de receita e desconto.
- [x] Exibir inadimplência por cliente e OS, com vencimento e total em atraso.
- [x] Criar um resumo simplificado para o proprietário conforme o período filtrado.
- [ ] Homologar valores, estornos, cancelamentos e fechamento de caixa com o responsável financeiro.

## 5. WhatsApp e notificações

- [x] Registrar tentativas, resultados e erros de envio.
- [x] Manter fallback manual por `wa.me`.
- [x] Suportar templates versionados e variáveis restritas.
- [x] Permitir retry administrativo de notificações.
- [x] Criar templates padrão editáveis para OS aberta, orçamento enviado, aprovado, pronto para retirada, cobrança e garantia. A aprovação final do texto ainda depende do proprietário/Meta.
- [x] Ligar abertura de OS, orçamento enviado/aprovado, mudança de status, cobrança pendente e retorno em garantia aos templates correspondentes, com fila idempotente e testes.
- [ ] Homologar templates e credenciais na Meta.
- [ ] Decidir se o gateway local continuará permitido e em quais ambientes.

## 6. Estoque, bancada, agenda e coleta

- [x] Baixa automática, estoque mínimo, histórico, lotes, fornecedor e sugestão de compra.
- [x] Produtos e serviços inativos não aparecem em novas OS.
- [x] Bancada por etapa, prioridade, prazo, checklist, laudo e aviso ao cliente.
- [x] Agenda de coleta/entrega, múltiplos pontos, rota externa, status, confirmação e comprovantes.
- [ ] Homologar contagem física e ajuste de estoque com dados reais do piloto.
- [ ] Confirmar rotas e comprovantes em um aparelho móvel real.

## 7. Portal e site público

- [x] Consulta pública de OS integrada ao site.
- [x] Status simples, prazo, aprovação, assinatura, comprovante, garantia e botão de WhatsApp.
- [x] Site e consulta possuem description, canonical, Open Graph e dados estruturados.
- [x] Páginas privadas e links de convite usam `noindex`.
- [ ] Publicar no domínio final e validar DNS, HTTPS, compartilhamento social e indexação.
- [ ] Fazer teste de usabilidade com clientes reais sem explicar previamente a tela.

## 8. Auditoria, permissões e LGPD

- [x] RBAC/ABAC, isolamento por empresa e restrições de financeiro/configuração testados.
- [x] Administrador pode revisar usuários, sessões, eventos e configurações críticas.
- [x] Ações centrais de clientes, OS, estoque, financeiro, usuários, privacidade e segurança geram auditoria.
- [x] Exportação, consentimento, anonimização e retenção estão implementados.
- [x] Criar uma [matriz formal das mutações](docs/AUDITORIA_MUTACOES.md), distinguindo `EventoLog` e trilhas especializadas.
- [ ] Fechar as lacunas de auditoria rota por rota listadas na matriz e confirmar tenant, tipo, módulo e ausência de dados sensíveis com testes.
- [ ] Aprovar juridicamente os prazos de retenção antes de ativá-los.
- [ ] Aprovar termos de uso, política de privacidade e natureza da assinatura eletrônica.

## 9. Experiência e homologação

- [x] Auditoria automatizada em 320 px, Pixel 7, tablet, desktop e wide.
- [x] Tema, menu, foco, modal, tabelas e ausência de overflow crítico testados.
- [x] Screenshots representativos revisados manualmente.
- [ ] Revisar português de todas as telas com revisor humano.
- [ ] Homologar dark mode página por página em aparelhos reais.
- [ ] Testar com atendente, técnico, proprietário e clientes com diferentes níveis de familiaridade digital.
- [ ] Avaliar divisão dos formulários longos de OS e laudo em etapas.
- [ ] Confirmar legibilidade de tabelas com usuários mais velhos.

## 10. Operação e comercialização

- [x] Instalação, configuração, deploy, rollback, observabilidade e recuperação documentados.
- [x] CI, release versionada, imagem imutável e deploy staging/produção disponíveis.
- [x] Checklist de go-live e política operacional documentados.
- [ ] Definir licença e condições de distribuição.
- [ ] Definir planos, preços, impostos e moeda. O adapter recorrente Asaas, checkout por API, cancelamento e webhooks já estão implementados; faltam credenciais e homologação.
- [ ] Definir SLA, canais, horários e responsáveis pelo suporte.
- [ ] Definir controlador LGPD e procedimento de atendimento ao titular.
- [ ] Executar piloto com uma assistência e registrar problemas por pelo menos um ciclo operacional.
- [ ] Aprovar formalmente o go-live após o piloto.

## Ordem recomendada

1. Salvar e publicar as correções verificadas.
2. Configurar staging com segredos, HTTPS, SMTP, alertas e WhatsApp.
3. Configurar backup externo e provar o restore.
4. Homologar o fluxo de OS, financeiro e PDFs com usuários reais.
5. Executar piloto controlado.
6. Corrigir os problemas do piloto.
7. Concluir decisões jurídicas e comerciais.
8. Executar o checklist de go-live.
9. Liberar produção gradualmente e monitorar.
