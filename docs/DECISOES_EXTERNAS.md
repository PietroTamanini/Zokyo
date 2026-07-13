# Decisoes externas

Estas escolhas nao podem ser feitas automaticamente pelo codigo. O sistema permanece funcional sem elas.

| Decisao | Responsavel | Condicao para implementar |
|---|---|---|
| Licenca do projeto | Proprietario/juridico | Escolher termos de distribuicao e comercializacao. |
| Precos e gateway real | Proprietario/comercial | Definir planos, moeda, tributos, gateway e credenciais de homologacao. O provider sandbox ja esta pronto. |
| Assinatura com validade juridica | Juridico | Definir assinatura simples ou ICP-Brasil e politica de evidencias. O PDF nao alega certificacao digital. |
| Backup externo | Infraestrutura/proprietario | Definir provedor, regiao, KMS/criptografia e prazos. Scripts locais produzem manifesto e verificam integridade. |
| Prazos de retencao | Controlador/juridico | Aprovar os prazos na tela administrativa. Nenhuma politica vem ativa. |
| API JSON de laudos | Produto/integrador | Identificar consumidor, autenticacao, campos e politica de versao. |
