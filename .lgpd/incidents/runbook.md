# Runbook de Incidentes de Dados Pessoais

**Base:** LGPD Art. 48; Res. CD/ANPD nº 15/2024, Arts. 5, 6, 9 e 10. [Orientação oficial da ANPD sobre comunicação de incidentes](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).

## Critério de decisão

Notificar quando houver risco/dano relevante **e** envolver dado sensível, criança/adolescente/idoso, financeiro, autenticação, sigilo ou larga escala (Res. 15/2024, Art. 5º). Mesmo sem notificação, registrar todos os incidentes por 5 anos (Art. 10).

## Fluxo T+0 a T+72h

1. Registrar horário exato em que se soube que dados pessoais foram afetados.
2. Acionar encarregado, segurança, jurídico e operador envolvido.
3. Conter sem destruir evidências: revogar tokens, isolar bucket, bloquear endpoint, preservar logs.
4. Identificar categorias, titulares, volume, causa, operador e risco.
5. Decidir por escrito se é notificável.
6. Se aplicável, comunicar ANPD e titulares em até 3 dias úteis; ATPP em dobro salvo risco à integridade.
7. Complementar investigação e atualizar o registro.

## Comunicação ANPD

Preparar natureza/categorias, titulares discriminados, medidas, riscos, mitigação, datas, encarregado, controlador, operador, causa e total de titulares (Res. 15/2024, Art. 6º, § 2º).

## Comunicação ao titular

Usar linguagem simples, individualizada quando possível, com natureza dos dados, medidas, riscos, mitigação, datas e contato do encarregado (Res. 15/2024, Art. 9º).

## Exercício anual

Simular vazamento de e-mails, privilégio excessivo, bucket/storage exposto, comprometimento de operador e ransomware. Cronometrar a triagem e a decisão.

## Registro no sistema

O super admin registra o incidente em `/privacidade/incidentes` e atualiza cada ocorrência pela sua rota específica. O horário de conhecimento de afetação a dados pessoais pode ficar em branco enquanto não confirmado; quando conhecido, deve ser informado em ISO 8601 com fuso horário (ex.: `2026-11-06T14:30:00-03:00`). Os horários de comunicação à ANPD e aos titulares, além de protocolo/referência, são registrados separadamente; o sistema valida fuso e ordem cronológica, mas não calcula feriados ou certifica cumprimento do prazo.

A tela exige decisão de comunicação e ações corretivas documentadas antes do encerramento; quantidade estimada de titulares negativa ou inválida é recusada. O registro no sistema não envia comunicações nem substitui o comprovante externo: a equipe responsável deve guardar o protocolo e as evidências conforme o fluxo acima.

Cada criação/atualização agora grava uma versão adicional em `privacy_incident_revisions` na mesma transação. O painel exibe estado, severidade, horários, decisão, ações e protocolo de cada versão. A migration `0045` registra um estado de referência para incidentes antigos e instala triggers que impedem UPDATE/DELETE dessas versões. Usuários com privilégio de alterar a estrutura do banco ainda podem remover triggers; segregação de privilégios, backup e retenção operacional continuam necessários. O histórico registra o que foi salvo no sistema, não comprova o envio externo da comunicação.

O job diário `monitorar_prazos_privacidade` sinaliza incidentes ainda abertos ou em investigação 24 horas depois do horário de conhecimento, se não houver decisão de comunicação registrada. Esse é um aviso de triagem antecipada, não uma determinação automática de notificabilidade ou cálculo de prazo legal. O painel de operações mostra a contagem.
