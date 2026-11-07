# DSAR — Workflow e Especificação

**Base:** LGPD Arts. 18 e 19, II; Res. 2/2022, Art. 14 quando ATPP aplicável. [Orientação da ANPD sobre direitos dos titulares](https://www.gov.br/anpd/pt-br/assuntos/titular-de-dados/direito-dos-titulares).

## Direitos cobertos

1. Confirmação de tratamento.
2. Acesso.
3. Correção.
4. Anonimização/bloqueio/eliminação de dados desnecessários.
5. Portabilidade.
6. Eliminação quando cabível.
7. Informação sobre compartilhamentos.
8. Informação sobre não consentir e consequências.
9. Revogação de consentimento.

## Canais

- API autenticada para titulares com conta/portal.
- Formulário público para quem não acessa o painel.
- Canal do encarregado, ainda pendente de designação.

## SLA e estados

- Padrão: 15 dias corridos para resposta completa (Art. 19, II).
- ATPP: validar prazo em dobro de 30 dias (Res. 2/2022, Art. 14).
- Estados implementados: `open`, `in_progress`, `completed`, `rejected`. Estados adicionais e suspensão por motivo legal ainda dependem de desenho e aprovação.
- O scheduler dedicado verifica diariamente pedidos vencidos e a vencer em até dois dias e cria alertas operacionais sem dados pessoais. A lista administrativa destaca pedidos vencidos. A regra não calcula feriados nem amplia automaticamente prazo; qualquer exceção exige análise e registro.

## Endpoints propostos

| Direito | Endpoint |
|---|---|
| Confirmação/acesso | `GET /api/me` e `GET /api/me/export` |
| Correção | `PATCH /api/me/profile` |
| Eliminação | `POST /api/me/erasure` |
| Compartilhamentos | `GET /api/me/sharing` |
| Revogação | `POST /api/consent/revoke` |
| Pedido não autenticado | `POST /api/privacy/requests` |
| Acompanhamento | `GET /api/privacy/requests/<id>` |

## Regras de segurança

- Verificar identidade com o mínimo necessário; não exigir dados excessivos.
- Verificar organização, titularidade e representação.
- Gerar exportação assinada/temporária, sem expor dados de outro tenant.
- Aplicar retenção legal: bloquear/anonimizar parcialmente quando não puder apagar.
- Registrar `DSAR_RECEIVED`, `DSAR_IDENTITY_VERIFIED`, `DSAR_FULFILLED` ou `DSAR_REJECTED` sem copiar PII no log.
- Manter evidência do pedido e decisão por no mínimo o prazo aprovado; incidentes relacionados, por 5 anos.

## Estado atual da implementação

- O formulário público em `/privacidade/solicitacao` e `/privacidade/solicitacao/<slug>` recebe pedidos sem exigir conta. A listagem do super admin em `/privacidade/solicitacoes` permite triagem; o prazo preliminar é gravado no pedido.
- O POST público tem limite adicional configurável por IP (`PRIVACY_REQUEST_LIMIT_PER_HOUR`, padrão 10 por hora), compartilhado entre o canal geral e os canais das assistências. Ao exceder, responde 429 com `Retry-After`, não grava pedido nem repete o e-mail enviado na página. Formulário, erros de validação e confirmação enviam `Cache-Control: no-store, private`; o texto do campo livre pede somente o mínimo necessário. O bucket dedicado usa HMAC com finalidade separada, e o limitador global/API também grava pseudônimos HMAC de 43 caracteres. O bloqueio de login usa outro pseudônimo HMAC; a migration `0054` converteu as chaves antigas sem descartar bloqueios ativos. A limpeza operacional é executada pelo scheduler quando configurado; não declarar anonimização completa nem limpeza automática garantida no protótipo sem scheduler.
- O catálogo público aceita confirmação, acesso, correção, anonimização, bloqueio, eliminação, portabilidade, informações gerais, compartilhamento, consequências de não consentir, revogação de consentimento e revisão de decisão automatizada. A inclusão da opção abre um pedido para análise; não executa o direito automaticamente.
- O texto público esclarece que o pedido é registrado no recebimento. A validação de identidade não reinicia o prazo. Confirmação e acesso simplificado exigem priorização operacional conforme a orientação da ANPD; automação de resposta imediata ainda falta.
- O formulário administrativo envia a atualização ao registro correto (`POST /privacidade/solicitacoes/<id>`). Para marcar identidade validada, exige método de conferência e protocolo sem anexar documento pessoal; a migration `0047` guarda também o horário e inclui os dados no histórico append-only. Para concluir um pedido, exige identidade validada, resposta, canal, horário com fuso e referência de entrega. A recusa exige motivo e os mesmos dados de entrega. O sistema registra essa evidência declarada pelo operador, mas não comprova automaticamente identidade ou recebimento externo.
- Após validar a identidade, o super admin pode vincular o pedido a um cliente pelo ID da empresa e do cliente. O servidor exige correspondência entre ambos e recusa transferir um vínculo já estabelecido para outro cliente ou empresa. O vínculo entra nas novas revisões append-only; snapshots anteriores não possuem esses campos. Essa associação é declarada pelo operador e requer conferência operacional da titularidade.
- A migration `0046` preserva estado de referência para pedidos anteriores e cria `data_subject_request_revisions`, com uma versão adicional em cada inserção/atualização. Triggers no banco bloqueiam UPDATE/DELETE comuns das versões, e a tela administrativa mostra o histórico. Um administrador com privilégio de alterar a estrutura do banco ainda pode remover triggers; segregar credenciais e preservar backups continua necessário.
- O job `monitorar_prazos_privacidade` alerta sobre pedidos vencidos ou a vencer em dois dias. O painel de operações apresenta a contagem de vencidos; a fila oferece filtro **Vencidas**, ordenado pelo prazo mais antigo. Alertas de mesma categoria usam mensagem estável para evitar multiplicação por variação de contagem. O job depende do scheduler dedicado e de canal de alerta configurado para entrega externa.
- Exportação administrativa auditada e remoção limitada de identificadores cadastrais existem para clientes; não concluem automaticamente pedidos de titulares. O arquivo exportado inclui manifesto de fotos e arquivos disponíveis de OS/laudos. O novo painel global de privacidade por empresa permite consultar essas operações; novas concessões manuais de consentimento ficam indisponíveis ali até haver evidência adequada de coleta.
- Na ficha do cliente, usar o motivo **solicitação do titular** para exportar exige um pedido com identidade validada e vínculo com aquele cliente e empresa. Para remover dados cadastrais, o pedido também deve estar em andamento e ser de eliminação ou anonimização. A auditoria registra o ID do pedido, sem copiar nome ou e-mail. Investigações exigem incidente da mesma empresa. Suporte, duplicidade e minimização ainda dependem de evidência externa e revisão operacional.
- O ZIP agora inclui e-mail do cadastro, coletas agendadas, solicitações vinculadas e mais campos técnicos dos laudos, além de OS, financeiro relacionado e consentimentos. Cada consulta usa empresa e cliente; um teste com registros propositadamente inconsistentes entre duas empresas comprovou exclusão dos dados da outra empresa. OS e transações usam listas explícitas de campos para não copiar custos internos, comissões, dados de técnicos ou payloads do gateway. O `LEIA-ME.txt` orienta revisar textos e imagens antes da entrega. O arquivo ainda não é portabilidade homologada nem resposta automática ao titular.
- Ao gerar o ZIP, o serviço calcula SHA-256 dos bytes finais e grava `zip_sha256` no evento imutável de auditoria. A resposta traz o mesmo valor em `X-Export-SHA256`. Guarde uma cópia protegida e confira seu hash antes de usar como evidência; no Windows, `Get-FileHash -Algorithm SHA256 <arquivo.zip>`, e em Linux/macOS, `sha256sum <arquivo.zip>`. O hash identifica o artefato gerado, mas não comprova envio, recebimento, revisão de terceiros nem conclusão do pedido.
- A migration `20261107_0050` acrescenta ao pedido o SHA-256 e o horário do último ZIP preparado com motivo `subject_request`. A gravação gera uma nova revisão append-only com o ID do administrador, e a tela de solicitações mostra o hash. Exportações por suporte ou incidente não alteram o pedido. Pedidos antigos permanecem sem evidência retroativa. O ZIP não é armazenado pelo sistema; o operador deve preservar uma cópia protegida se precisar comprovar qual arquivo foi preparado. A geração não marca entrega nem conclusão.
- Exportação de suporte e remoção por duplicidade/minimização exigem um código de protocolo externo (4 a 40 caracteres, letras maiúsculas, números ou hífens), registrado no evento de auditoria. O código evita justificativas vazias e reduz o risco de copiar texto pessoal no log, mas o sistema ainda não verifica a existência nem a aprovação do atendimento externo. Manter a evidência fora do ZIP, em repositório de acesso controlado.
- Os endpoints da tabela acima continuam propostas, e não devem ser apresentados como APIs implementadas. Faltam atendimento automatizado de todos os direitos, confirmação externa da identidade por canal, portabilidade homologada, propagação a operadores e verificação externa da entrega da resposta ao titular. Registros legados com estado final podem não conter método/protocolo de identidade nem evidência de entrega; devem ser revisados antes de uso como prova.
