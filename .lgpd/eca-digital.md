# ECA Digital — Avaliação de aplicabilidade e plano

**Data:** 2026-11-06  
**Status:** avaliação preventiva aberta; enquadramento por fluxo e implementação pendentes  
**Escopo:** portal público, sites publicados e qualquer fluxo do sistema acessível por menores  
**Responsável:** produto + segurança + jurídico/encarregado — pendente de designação

## Conclusão atual

O responsável informou que o sistema pode ser acessado por menores. O produto não foi descrito como dirigido especificamente a crianças ou adolescentes. A possibilidade de acesso exige avaliação por fluxo da Lei nº 15.211/2025 (ECA Digital), especialmente nos fluxos públicos e de atendimento; **não prova, sozinha, o enquadramento definitivo de cada tela**. O [guia da ANPD publicado em 28/10/2026](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-publica-guia-que-esclarece-quem-deve-cumprir-e-quais-sao-as-responsabilidades-das-plataformas-na-protecao-de-criancas-e-adolescentes) orienta analisar em conjunto atratividade/probabilidade de uso, facilidade de acesso e riscos significativos.

Este documento é uma avaliação técnica inicial, não um parecer jurídico. Até a implementação e validação das medidas abaixo, o risco permanece **alto/pendente**.

## Situação encontrada

- Não foi comprovado mecanismo confiável de verificação de idade quando necessário.
- Não foi comprovado vínculo de responsável legal para usuários menores.
- Não foi comprovado controle parental configurável.
- Não foi identificado fluxo de publicidade comportamental ou venda de perfil de menores; ainda assim, isso deve ser proibido por política e controles técnicos.
- O produto não é um jogo e não possui loot boxes; esse requisito é considerado não aplicável no escopo atual.
- Não há evidência de volume superior a 1 milhão de usuários menores que exija relatório de transparência específico.
- O acesso por menores e o tratamento de dados de clientes/atendimentos devem alimentar a avaliação de impacto/RIPD quando o desenho final estiver definido.

## Inventário técnico dos fluxos que podem alcançar menores

| Fluxo | Evidência no código | Dado/ação | Controle atual | Decisão pendente |
|---|---|---|---|---|
| Site da assistência | `app/routes/public_site.py`, `app/services/tenant_site_bundle.py` | HTML/CSS/JS enviado pela assistência e entregue ao público | Publicação por tenant e isolamento do ZIP | Classificar conteúdo de cada site e integrações externas; verificar se existe conteúdo impróprio ou publicidade direcionada |
| Consulta pública de OS | `/consulta-os`, `POST /api/public/os-consulta` | Número da OS e CPF/CNPJ; resposta de acompanhamento | Validação de documento, tenant e limitação de consultas | Definir se menor titular ou responsável pode consultar e qual dado mínimo deve aparecer |
| Portal de orçamento | `GET/POST /portal/os/<token>` e PDF | Status, histórico e aprovação de orçamento com token | Token verificado, resposta sem cache e fora de indexação | Definir representação/autoridade para aprovação quando o cliente for menor |
| API de cliente | `/api/v1/client/*` | Dados de cliente, OS e cobrança; criação de OS | Token de portal e isolamento por assistência | Definir se menor recebe token e quais operações precisam de responsável |
| Solicitação de privacidade | `/privacidade/solicitacao` | Nome, e-mail e tipo de direito | Registro e validação manual de identidade para conclusão | Definir atendimento a menor e representante legal com minimização de dados |
| Painel interno | `/login` e módulos autenticados | Dados de funcionários, clientes e operação | Login e papéis; sem classificação etária | Confirmar se menores terão conta de funcionário/administrador |

Este inventário descreve pontos de entrada e riscos observados no código; não estima faixa etária real, tráfego ou adequação jurídica. Sites enviados por empresas podem incluir código e provedores externos que não aparecem no backend.

O dever de **verificação confiável a cada acesso do Art. 9º, §1º** se refere ao conteúdo, produto ou serviço impróprio, inadequado ou proibido para menores indicado no caput. Não se deve inferir uma exigência universal de verificar idade em toda consulta de OS apenas porque um menor pode acessá-la. A aplicação de aferição de idade, vínculo com responsável e controles parentais depende da classificação concreta de cada fluxo e da orientação jurídica. [Texto da lei](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/l15211.htm).

## Medidas obrigatórias a decidir e implementar

1. Definir, com jurídico, quais fluxos podem ser acessados por menores e se algum deles exige verificação confiável de idade, sem depender apenas de autodeclaração.
2. Implementar vínculo e autorização de responsável legal quando exigido, com registro mínimo, finalidade clara e mecanismo de revogação.
3. Bloquear publicidade comportamental, perfilização comercial e uso secundário dos dados de menores.
4. Disponibilizar controles parentais e informações claras, acessíveis e adequadas à idade.
5. Definir canal de denúncia, resposta e remoção para conteúdo ou comportamento ilícito, caso o portal permita conteúdo gerado por usuários.
6. Revisar contratos e papéis: a assistência é controladora dos dados dos seus clientes; a Zokyo atua principalmente como operadora, salvo tratamentos próprios do SaaS.
7. Produzir RIPD/avaliação de impacto para os fluxos de maior risco antes da liberação ampla.
8. Registrar decisões, testes, incidentes e revisões em trilha de auditoria com acesso restrito.

## Critérios de aceite

- Matriz de fluxos com público provável, idade, dados coletados, finalidade e base legal.
- Verificação de idade e responsável implementada somente onde necessária e validada contra minimização.
- Controles de perfilização/publicidade proibida cobertos por testes automatizados.
- Avisos de privacidade e telas adequados ao público, versionados e revisados juridicamente.
- RIPD aprovado ou justificativa documentada de não aplicabilidade para cada fluxo analisado.

## Próxima revisão

Revisar após a definição do público-alvo, fluxos públicos, integrações e política de privacidade. A revisão deve ocorrer antes da publicação dos novos fluxos e, no máximo, em seis meses.
