# Homologacao e evidencias

Use este roteiro para fechar os itens de `oque_falta.md` que dependem de ambiente real, usuarios, juridico, comercial ou operacao. Nao registre senhas, tokens, documentos completos, payloads de gateway nem dados pessoais desnecessarios.

## Registro minimo por item

| Campo | Preenchimento |
|---|---|
| Item do checklist | Referencia exata do `oque_falta.md` ou `GO_LIVE.md`. |
| Responsavel | Pessoa que executou ou aprovou. |
| Data e ambiente | Data, staging/producao/piloto e versao/tag implantada. |
| Evidencia | Saida de comando, screenshot redigido, protocolo, e-mail de aprovacao ou ata. |
| Resultado | Aprovado, reprovado ou aprovado com restricao. |
| Acao corretiva | Link para issue/tarefa quando houver pendencia. |

## Ambiente real

- Confirmar `FLASK_ENV=production`, `REQUIRE_ADMIN_2FA=true`, `PUBLIC_BASE_URL` HTTPS, `REDIS_URL`, `REPORTS_UPLOAD_FOLDER` privado e segredos no cofre.
- Executar `flask --app wsgi:app production-check --strict-integrations` e anexar a saida sem segredos.
- Confirmar `/healthz`, `/readyz` e metricas pelo dominio final.
- Validar SMTP com recuperacao de senha de uma conta controlada.
- Validar alerta operacional com `ALERT_EMAIL` ou `ALERT_WEBHOOK_URL`.
- Validar WhatsApp oficial ou anexar aprovacao formal de operacao apenas com fallback manual.

## Backup e restore

- Registrar provedor, regiao, politica de retencao, responsavel e local do runbook.
- Executar backup de banco e storage, criptografar, enviar para destino externo e registrar hashes/manifestos.
- Restaurar em ambiente descartavel e validar login, abertura de OS, PDF de laudo e arquivos privados.
- Registrar data do proximo teste mensal de restore e da simulacao trimestral de desastre.

## Produto e piloto

- Cronometrar abertura de OS com atendente real e registrar tempo, duvidas e ajustes.
- Homologar busca de cliente com base grande e nomes/documentos semelhantes.
- Executar ciclo completo: abertura, orcamento, aprovacao, pagamento parcial, entrega e garantia.
- Conferir PDF em tela e impressora real com identidade da assistencia.
- Homologar financeiro com responsavel: valores, estornos, cancelamentos e fechamento de caixa.
- Homologar estoque fisico, ajuste, rotas/coleta e comprovantes em aparelho movel real.

## Juridico e comercial

- Anexar aprovacao de termos de uso, politica de privacidade, prazos de retencao e natureza da assinatura.
- Registrar decisao de licenca/distribuicao, planos, precos, impostos, moeda, SLA, canais e horarios.
- Registrar controlador LGPD e procedimento de atendimento ao titular.

## Experiencia

- Revisar portugues com revisor humano e registrar lista de alteracoes.
- Homologar dark mode pagina por pagina em aparelhos reais.
- Testar com atendente, tecnico, proprietario e clientes sem explicacao previa.
- Avaliar formularios longos de OS/laudo e legibilidade de tabelas com usuarios mais velhos.
