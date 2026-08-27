# Política de suporte e operação

Este documento é um modelo operacional. Antes da venda, o proprietário deve preencher canais, horários, responsáveis e níveis de serviço reais.

## Escopo

O suporte cobre acesso ao sistema, indisponibilidade, erros funcionais, recuperação de dados, integrações configuradas e orientação de uso documentado. Treinamento adicional, customizações, dispositivos do cliente e serviços de terceiros devem ter condições comerciais próprias.

## Canais e responsáveis

| Item | Definição antes do go-live |
|---|---|
| Canal principal | E-mail, portal ou telefone oficial |
| Horário de atendimento | Dias, horário e fuso |
| Plantão crítico | Responsável e forma de acionamento |
| Responsável técnico | Nome/função |
| Responsável pelo cliente | Nome/função |
| Status público | Página ou canal de comunicação |

Nunca solicite senha, código TOTP, código de recuperação ou chave privada em chamado.

## Classificação sugerida

| Severidade | Exemplo | Resposta alvo a definir |
|---|---|---|
| Crítica | Sistema indisponível, perda/corrupção de dados ou vazamento suspeito | Imediata/plantão |
| Alta | Fluxo principal bloqueado sem alternativa segura | Horas úteis |
| Média | Função parcial com alternativa conhecida | Próximo ciclo acordado |
| Baixa | Dúvida, melhoria visual ou solicitação não bloqueante | Backlog priorizado |

Os tempos somente viram SLA após aprovação comercial e capacidade de atendimento confirmada.

## Atendimento de incidente

1. Registrar horário, organização afetada, usuário, rota, request ID e comportamento observado.
2. Classificar impacto sem copiar dados pessoais desnecessários.
3. Verificar healthchecks, logs, métricas, integrações e mudanças recentes.
4. Conter o impacto; usar rollback se a versão implantada for a causa provável.
5. Restaurar serviço e validar com o usuário afetado.
6. Preservar evidências de segurança e notificar os responsáveis quando aplicável.
7. Produzir análise de causa para incidentes críticos/altos e criar ações preventivas.

## Backup e recuperação

- Backup do banco e storage deve ser diário, criptografado e externo ao host.
- Falha ou vencimento deve gerar alerta.
- Restore deve ser testado mensalmente e desastre completo, trimestralmente.
- Recuperação segue [BACKUP_RESTORE.md](BACKUP_RESTORE.md) e [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).
- Exclusões e restaurações em produção exigem autorização e registro de auditoria operacional.

## Atualizações

- Mudanças passam por CI, staging e checklist de go-live proporcional ao risco.
- Banco é atualizado somente por migrations Alembic.
- Produção usa imagem imutável e tag/commit identificável.
- Toda implantação deve ter caminho de rollback e responsável acompanhando healthchecks.
- Correções urgentes recebem posteriormente testes e registro no changelog.

## Privacidade e segurança

Incidentes com possível exposição de dados devem ser encaminhados imediatamente ao controlador/encarregado definido pela organização. Logs e chamados devem minimizar CPF/CNPJ, telefone, endereço, e-mail, tokens e conteúdo técnico privado.

## Encerramento de cliente

Antes de cancelar uma organização, defina exportação, retenção, anonimização, revogação de acessos, destino dos backups e prazo de exclusão. A decisão deve respeitar contrato, obrigação legal e política LGPD aprovada.
