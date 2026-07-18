# O que falta para o Zokyo ficar ainda mais profissional

Atualizado em 2026-07-18 apos nova varredura local de seguranca, testes e interface publica.

O sistema esta funcional e possui uma base ampla de seguranca, testes e operacao. Este arquivo registra somente entregas comprovadas e pendencias reais.

## Resumo atual

- 74 itens concluidos no repositorio.
- 5 ativacoes externas pendentes.
- 174 testes Python aprovados.
- Playwright publico revalidado em cinco viewports: 20 cenarios aprovados.
- Auditoria Playwright autenticada ampla continua dependente de `E2E_EMAIL` e `E2E_PASSWORD` reais.
- Cobertura automatizada atual: 100% global e 100% no nucleo de dominio/servicos.
- MariaDB na revisao Alembic `20260712_0026`.
- `pip-audit` e `npm audit` sem vulnerabilidades conhecidas.
- Compose YAML valido; container local nao foi revalidado neste ambiente porque Docker nao esta instalado.

## Situacao da fase interna

O roadmap implementavel no repositorio foi concluido. Os itens restantes exigem
dominio, servidor, credenciais, contrato ou uma execucao humana no ambiente real.

## Prioridade alta

### 1. Backup automatico validado

- [x] Scripts de backup diario e criptografia autenticada prontos para agendamento.
- [x] Automacao de copia externa criptografada, imutavel e verificada via `rclone`; ativar um destino real ainda exige credenciais.
- [x] Retencao local configuravel implementada.
- [x] Restauracao e integridade testadas automaticamente.
- [x] Emitir alerta seguro por webhook em falha ou backup vencido.

### 2. Producao com HTTPS

- [ ] Configurar um dominio proprio.
- [ ] Instalar e renovar automaticamente o certificado TLS.
- [ ] Expor somente as portas `80` e `443` no firewall.
- [x] MariaDB sem porta publica no Compose de producao.
- [ ] Armazenar segredos em um cofre apropriado, fora do repositorio.
- [x] Configuracoes separadas para desenvolvimento e producao; homologacao depende do host escolhido.
- [x] Gate executavel `production-check --strict-integrations` para reprovar configuracao incompleta antes de publicar.

### 3. Recuperacao e continuidade

- [x] Procedimento documentado em `docs/DISASTER_RECOVERY.md`.
- [x] RTO inicial de quatro horas definido.
- [x] RPO inicial de 24 horas definido.
- [x] Processo seguro de rollback documentado.
- [ ] Executar simulacoes trimestrais no ambiente real.

### 4. Observabilidade completa

- [x] Integracao opcional com Sentry implementada sem PII por padrao.
- [x] Monitorar CPU/load, disco, rede, pool/conexoes do banco e filas.
- [x] Healthchecks, readiness, metricas e latencia implementados.
- [x] Alertar sobre falhas no scheduler e nas notificacoes, com heartbeat persistente.
- [x] Dashboards Grafana e regras Prometheus por severidade versionados em `monitoring/`.

### 5. Seguranca operacional

- [x] 2FA obrigatorio para administradores em producao, configuravel por ambiente.
- [x] Exibir sessoes e dispositivos ativos por usuario, com IP, agente, atividade e revogacao individual.
- [x] Revogacao imediata de todas as sessoes por usuario.
- [x] Politica central de senha forte implementada.
- [x] Processo de conta comprometida com revogacao e auditoria.
- [x] Varredura de CVEs altas/criticas da imagem Docker no CI.
- [x] Testes de autorizacao e isolamento entre empresas no CI diario.

## Recursos comerciais

### 6. Atendimento e ordens de servico

- [x] Checklists tecnicos versionados por categoria, com snapshot imutavel na OS.
- [x] Capturar assinatura eletronica do cliente com evidencia, hash, IP, usuario, data e imagem privada; eventual ICP-Brasil depende da politica juridica.
- [x] Fotos privadas de OS e laudos organizadas e validadas.
- [x] Termo de autorizacao, aceite auditado e inclusao no PDF da OS.
- [x] Historico auditavel da OS implementado.
- [x] Aprovacao ou rejeicao por token temporario seguro.
- [x] Prazo e situacao de garantia registrados; classificacao de reincidencia ainda pode evoluir.

### 7. Comunicacao profissional

- [x] Portal publico minimo e seguro implementado.
- [x] Acompanhamento e decisao por token com hash, expiracao e revogacao.
- [x] Templates versionados por evento e canal com variaveis restritas.
- [x] E-mail transacional integrado a fila persistente e SMTP.
- [x] Notificacoes de mudanca de status e conclusao; lembretes proativos de atraso ainda podem evoluir.
- [x] Integracao direta com a API oficial Meta WhatsApp Cloud, com fallback manual e gateway legado opcional; ativacao exige credenciais Meta.
- [x] Fila persistente registra tentativas, entrega, erros e retry exponencial.

### 8. Estoque avancado

- [x] Inventario e ajustes com justificativa e livro imutavel de movimentos.
- [x] Reservas de pecas por OS, consumo e cancelamento auditados.
- [x] Lotes fisicos, validade, fornecedor e livro imutavel de movimentacoes implementados.
- [x] Sugestoes de compra calculadas pelo disponivel e estoque minimo.
- [x] Campo de codigo pronto para leitores que operam como teclado.
- [x] Custo medio ponderado atualizado transacionalmente a cada entrada de lote.
- [x] Estoque minimo e bloqueio de operacoes inconsistentes implementados.

### 9. Financeiro completo

- [x] Receitas, despesas, vencimento, pagamento e status implementados.
- [x] Parcelamento em ate 60 vezes e recorrencia mensal com fechamento exato de centavos.
- [x] Conciliacao e desconciliacao financeira auditadas.
- [x] Fluxo realizado e pendencias por vencimento disponiveis.
- [x] Comissoes por usuario com percentual e valor por parcela.
- [x] DRE simplificada por periodo e categoria.
- [x] Exportacao contabil CSV protegida contra formula injection.

### 10. Relatorios gerenciais

- [x] Margem estimada e dados por OS/cliente/tecnico disponiveis.
- [x] Tempo medio de atendimento calculado.
- [x] OS em garantia contabilizadas; reincidencia detalhada permanece evolucao.
- [x] Conversao de orcamentos calculada.
- [x] Clientes recorrentes e inativos identificados.
- [x] Exportacoes CSV, XLSX e PDF protegidas contra formula injection.
- [x] Filtros salvos e relatorios agendados por e-mail no scheduler dedicado.

## Evolucao SaaS

### 11. Multiempresa maduro

- [x] Planos, recursos e limites tecnicos implementados.
- [x] Assinaturas e webhook sandbox implementados; provedor real depende de contrato.
- [x] Convites de usuario com token em hash, uso unico, expiracao e envio por e-mail.
- [x] Nome e cores da identidade visual configuraveis por empresa.
- [x] Bloqueio de escrita por situacao da assinatura implementado.
- [x] Painel global da plataforma implementado.
- [x] Medir usuarios, clientes, OS, armazenamento e ultima atividade por organizacao.

### 12. Qualidade e entrega

- [x] Cobertura do nucleo de dominio e servicos em 100%, com gate minimo de 80%; cobertura global atual de 100%.
- [x] Testes de concorrencia e isolamento multiempresa implementados.
- [x] Teste de carga reproduzivel com concorrencia, taxa de erro e limite de p95 no CI.
- [x] CI/CD com imagem imutavel, homologacao, aprovacao por Environment, healthcheck e rollback automatico versionado.
- [x] Releases por tag semantica validadas, auditadas, construidas e publicadas com notas automaticas; incremento da versao continua deliberadamente manual.
- [x] Dependencias, codigo e segredos auditados diariamente no CI.
- [x] Migracoes em MariaDB limpo e restauradores verificados no pipeline.
- [x] CI e release executam o contrato de prontidao de producao em modo estrito.

## Dependencias externas

Permanecem necessariamente dependentes de contratacao, credenciais ou decisao do proprietario:

- Dominio, DNS, certificado TLS e regras do firewall do servidor.
- Cofre de segredos e credenciais do destino externo imutavel para backups.
- Ativacao dos dashboards e canais de alerta no host escolhido.
- Credenciais do WhatsApp Business oficial e do e-mail transacional.
- Politica juridica para assinatura digital.
- Provedor real de cobranca recorrente.
- Hosts e credenciais de homologacao e producao para CI/CD.

Os pontos de integracao foram preparados sem armazenar credenciais no repositorio.

## Proximas acoes do proprietario

1. Contratar/configurar dominio, DNS, host e certificado TLS.
2. Restringir o firewall do host a SSH administrativo e portas publicas `80/443`.
3. Configurar cofre de segredos, destino `rclone`, Prometheus/Grafana e canais de alerta.
4. Cadastrar credenciais Meta/SMTP e proteger o Environment `production` com aprovadores.
5. Executar e registrar a primeira restauracao real; repetir trimestralmente.

> Nenhum sistema pode garantir ausencia absoluta de vulnerabilidades. A meta profissional deve ser manter zero vulnerabilidades conhecidas, reduzir continuamente a superficie de ataque e responder rapidamente a novos riscos.
