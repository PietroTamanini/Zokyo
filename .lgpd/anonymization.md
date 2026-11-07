# Anonimização e Pseudonimização — Plano

**Status:** especificação inicial; nenhum dataset foi declarado anonimizado.

O botão administrativo de cliente foi revisado em 2026-11-06 para **remoção de identificadores cadastrais**. Ele não comprova anonimização: eventos imutáveis, consentimentos, pedidos de titulares, backups e outros vínculos podem conservar a identidade. OS, laudos e coletas vinculadas bloqueiam a remoção; a revisão de todas as dependências e o teste de reidentificação continuam necessários antes de atender um pedido de anonimização como concluído.

## Aplicação no Zokyo

- **Pseudonimização:** analytics internas, logs e métricas devem usar token determinístico com segredo separado; continua sendo dado pessoal (Art. 13, § 4º).
- **Anonimização:** relatórios públicos ou datasets de pesquisa devem remover/suprimir identificadores, generalizar cidade/CEP e avaliar unicidade com k-anonymity mínimo a definir (Art. 5º, XI e Art. 12).
- CPF/e-mail/telefone não devem ser tratados como anônimos apenas por hash; índices cegos são controle de busca, não anonimização.

## Checklist antes de liberar dataset

- [ ] Finalidade e base legal aprovadas.
- [ ] Campos diretos e quasi-identificadores inventariados.
- [ ] Chave/vault de pseudônimos separado e com acesso restrito.
- [ ] Teste de singling-out, linkage e inference executado.
- [ ] Generalização/supressão documentada.
- [ ] Risco residual aprovado pelo encarregado.
- [ ] Dataset e versão registrados no ROPA.
