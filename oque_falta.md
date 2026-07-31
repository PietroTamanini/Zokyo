# O que falta para o Zokyo ficar top dos tops

Atualizado em 2026-07-31.

O sistema ja esta grande. O proximo salto nao e colocar qualquer modulo novo sem criterio. O que falta agora e fechar produto: seguranca real, fluxo simples, operacao diaria sem travar e uma experiencia que qualquer funcionario consiga usar sem medo.

## Prioridade 1: producao blindada

- [ ] Configurar ambiente real com `FLASK_ENV=production`.
- [ ] Usar `SECRET_KEY`, `ENCRYPTION_SALT`, `FIELD_ENCRYPTION_KEY`, `BLIND_INDEX_KEY` e `BACKUP_ENCRYPTION_KEY` fortes, fora do repositorio.
- [ ] Ativar HTTPS no dominio principal e no painel.
- [ ] Configurar `PUBLIC_BASE_URL` ou `HEALTHCHECK_URL` com URL publica HTTPS.
- [ ] Ativar `REQUIRE_ADMIN_2FA=true` em producao.
- [ ] Configurar SMTP real para recuperacao de senha e avisos importantes.
- [ ] Configurar canal de alerta operacional por e-mail ou webhook.
- [ ] Rodar `flask --app wsgi:app production-check --strict-integrations` e so publicar quando passar sem erro.

## Prioridade 2: backup e restore de verdade

- [ ] Agendar backup automatico diario do MySQL/MariaDB.
- [ ] Agendar backup dos uploads e arquivos privados.
- [ ] Criptografar backups antes de enviar para fora do servidor.
- [ ] Enviar backup para destino externo confiavel.
- [ ] Testar restore em banco descartavel antes de colocar cliente real.
- [ ] Criar rotina mensal de verificacao de restore.
- [ ] Monitorar falha de backup e backup vencido.

## Prioridade 3: fluxo de OS impecavel

- [ ] Abrir OS em menos de 1 minuto.
- [ ] Melhorar busca de cliente para nao cortar resultado nem confundir usuario.
- [ ] Deixar equipamento, defeito, checklist, fotos e assinatura em uma ordem simples.
- [ ] Garantir que orcamento, aprovacao, pagamento parcial e finalizacao estejam travados corretamente.
- [ ] Impedir finalizacao de OS sem 100% de pagamento.
- [ ] Manter OS baixada/arquivada fora da tela principal.
- [ ] Deixar PDF da OS bonito, direto para imprimir e consistente com a identidade da assistencia.
- [ ] Validar fluxo completo: criar OS, editar, aprovar, pagar, imprimir, baixar e consultar no portal.

## Prioridade 4: painel de bancada para tecnico

- [ ] Criar visao rapida de OS por etapa.
- [ ] Destacar prioridade, prazo e status.
- [ ] Mostrar pecas necessarias e links de compra apenas para tecnico.
- [ ] Separar observacao interna da observacao do cliente.
- [ ] Facilitar checklist tecnico.
- [ ] Facilitar criacao de laudo.
- [ ] Ter botao claro para avisar cliente.

## Prioridade 5: WhatsApp profissional

- [ ] Configurar WhatsApp Cloud API oficial da Meta para producao.
- [ ] Manter gateway local apenas como alternativa controlada/teste.
- [ ] Criar templates configuraveis por status.
- [ ] Ter mensagens para OS aberta, orcamento enviado, aprovado, pronto para retirada, cobranca pendente e garantia.
- [ ] Registrar tentativas, erros e entregas.
- [ ] Manter fallback manual por `wa.me` quando a API estiver indisponivel.

## Prioridade 6: financeiro inteligente

- [ ] Mostrar quanto entrou hoje.
- [ ] Mostrar quanto esta pendente.
- [ ] Mostrar OS com pagamento incompleto.
- [ ] Calcular lucro por OS.
- [ ] Separar custo de peca, mao de obra e desconto.
- [ ] Mostrar inadimplencia.
- [ ] Gerar relatorio mensal simples para o dono.

## Prioridade 7: estoque realmente util

- [ ] Baixar estoque automaticamente ao usar peca na OS.
- [ ] Alertar estoque baixo.
- [ ] Mostrar historico de movimentacao.
- [ ] Vincular fornecedor a peca.
- [ ] Sugerir compra quando estoque estiver baixo.
- [ ] Evitar que produto ou servico inativo apareca em novas OS.

## Prioridade 8: portal do cliente

- [ ] Melhorar consulta publica da OS no dominio principal.
- [ ] Mostrar status em linguagem simples.
- [ ] Mostrar prazo estimado.
- [ ] Permitir aprovacao de orcamento pelo cliente.
- [ ] Permitir assinatura digital quando fizer sentido.
- [ ] Mostrar comprovante e garantia.
- [ ] Ter botao de WhatsApp sempre visivel.
- [ ] Melhorar SEO da pagina de consulta e do site publico.

## Prioridade 9: agenda, coleta e rota

- [ ] Criar agenda de coletas e entregas.
- [ ] Usar endereco da assistencia como origem e destino padrao.
- [ ] Permitir varios pontos de coleta.
- [ ] Calcular melhor rota com GPS/mapa.
- [ ] Registrar status da coleta.
- [ ] Registrar confirmacao do cliente.
- [ ] Permitir foto ou comprovante na retirada e entrega.

## Prioridade 10: auditoria, permissoes e seguranca interna

- [ ] Garantir que toda acao importante gere log de auditoria.
- [ ] Separar permissoes por cargo.
- [ ] Tecnico nao deve ver financeiro sensivel sem permissao.
- [ ] Atendente nao deve alterar configuracao critica.
- [ ] Admin deve conseguir revisar sessoes, logs e usuarios.
- [ ] Revisar RBAC e ABAC rota por rota.
- [ ] Validar isolamento entre empresas/usuarios.

## Prioridade 11: polimento visual pagina por pagina

- [ ] Revisar portugues de todas as telas.
- [ ] Padronizar botoes, icones, cores e espacamentos.
- [ ] Garantir dark mode bonito em todas as paginas.
- [ ] Corrigir cortes no mobile.
- [ ] Reduzir poluicao visual dos formularios.
- [ ] Melhorar tabelas grandes para pessoas mais velhas usarem sem dificuldade.
- [ ] Rodar Playwright autenticado em compact, mobile, tablet, desktop e wide.

## Prioridade 12: operacao e venda

- [ ] Documentar instalacao local para suporte.
- [ ] Documentar instalacao em producao.
- [ ] Criar checklist antes de colocar cliente real.
- [ ] Criar rotina de atualizacao sem perder dados.
- [ ] Criar politica de suporte, backup e recuperacao.
- [ ] Validar cobranca recorrente antes de vender acesso para terceiros.

## Ordem certa de execucao

1. Producao segura.
2. Backup e restore testados.
3. OS perfeita.
4. WhatsApp real.
5. Financeiro e estoque confiaveis.
6. Portal do cliente.
7. Agenda e coleta.
8. Auditoria e permissoes.
9. Polimento visual final.
10. Operacao comercial.

## Observacao direta

O sistema nao precisa de mais acumulacao aleatoria de funcoes. Ele precisa ficar simples, confiavel e impossivel de quebrar na mao de funcionario comum. Esse e o caminho para virar um sistema realmente profissional para assistencia tecnica.
