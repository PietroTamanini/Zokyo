# Prompt Codex — Zokyo: PWA, Coleta, Cliente e Importação CPlus/Firebird

Você vai trabalhar no projeto **Zokyo**, um sistema Flask + SQLAlchemy + Jinja2 + JavaScript Vanilla + MySQL para assistência técnica e ordens de serviço.

Estou enviando junto:

1. o código-fonte completo do projeto Zokyo;
2. o banco de dados Firebird `.fdb` real exportado do sistema **CPlus**.

Sua tarefa é implementar exatamente os requisitos abaixo.

Antes de qualquer alteração, faça uma análise completa do projeto e do banco `.fdb`.

---

# REGRA OBRIGATÓRIA SOBRE O BANCO CPLUS

Você NÃO deve começar chutando nomes de tabelas.

Você NÃO deve assumir que existem tabelas chamadas `CLIENTES`, `PRODUTOS`, `OS`, `ORDENS`, `ESTOQUE` ou qualquer outro nome sem verificar.

Você DEVE primeiro abrir/analisar o schema real do arquivo `.fdb`.

Antes de codar a importação, você precisa descobrir e documentar:

- todas as tabelas existentes;
- colunas de cada tabela;
- tipos de dados;
- chaves primárias;
- possíveis chaves estrangeiras;
- relacionamentos prováveis;
- tabelas que provavelmente representam clientes;
- tabelas que provavelmente representam produtos, peças ou estoque;
- tabelas que provavelmente representam ordens de serviço;
- tabelas auxiliares, como cidades, endereços, telefones, categorias, marcas, técnicos etc.

Depois disso, crie um relatório técnico com:

- tabelas encontradas no `.fdb`;
- quais tabelas serão usadas na importação;
- quais campos serão mapeados para o Zokyo;
- quais campos serão ignorados;
- quais dados precisam de tratamento;
- quais dados não podem ser importados com segurança;
- quais partes precisam de confirmação manual.

Se o schema real do banco CPlus não permitir importar algum dado com segurança, diga claramente. Não invente mapeamento falso.

Se você começar a importação usando nomes de tabelas inventados sem analisar o `.fdb`, a tarefa estará errada.

---

# 1. Objetivo geral

Implementar no Zokyo:

1. módulo de coleta para celular;
2. PWA instalável no celular;
3. correção dos erros de formulário para manter dados preenchidos;
4. alteração do cadastro de cliente;
5. suporte a CPF/CNPJ inteligente;
6. remoção do e-mail do cadastro de cliente;
7. adição de número da casa;
8. cliente rápido dentro da OS;
9. importação real do banco Firebird `.fdb` do CPlus para o Zokyo.

Não reescreva o sistema inteiro.

Não troque a stack.

Não transforme em React, Vue ou SPA.

Não quebre:

- login;
- usuários;
- dashboard;
- estoque;
- financeiro;
- fornecedores;
- WhatsApp;
- PDF;
- rotas existentes.

---

# 2. Dependência Firebird

Adicionar suporte a Firebird no projeto.

Preferência:

```txt
firebird-driver>=1.10
```

Se o ambiente ficar mais compatível com outra biblioteca, pode usar:

```txt
fdb>=2.0.2
```

Atualize o `requirements.txt`.

Atualize o `README.md` explicando que para importar `.fdb`, a máquina precisa ter o client/server Firebird instalado.

O sistema não pode quebrar se Firebird não estiver instalado. Deve mostrar erro amigável.

---

# 3. Serviço de importação CPlus

Criar serviço separado:

```txt
app/services/cplus_firebird_importer.py
```

Esse serviço deve ser responsável por:

- conectar no `.fdb`;
- testar conexão;
- listar tabelas;
- listar colunas;
- detectar entidades prováveis;
- mapear dados do CPlus para o Zokyo;
- fazer preview;
- importar somente após confirmação;
- evitar duplicidade;
- registrar log técnico da importação.

Não colocar lógica pesada de importação direto nas rotas.

---

# 4. Tela admin de importação

Criar tela protegida para admin:

```txt
/importacao/cplus
```

Criar rotas/API protegidas:

```txt
POST /api/importacao/cplus/test
POST /api/importacao/cplus/preview
POST /api/importacao/cplus/commit
```

Se o projeto usar outro padrão de rotas, adapte ao padrão existente.

A tela deve permitir:

- informar caminho do `.fdb` no servidor;
- usuário Firebird;
- senha Firebird;
- charset, padrão `WIN1252`;
- testar conexão;
- pré-visualizar dados;
- confirmar importação.

Não salvar senha Firebird em banco.

Não salvar senha Firebird em log.

Não mostrar senha Firebird na tela.

Não expor rota de importação para usuário comum.

Importação é apenas para admin.

---

# 5. Preview obrigatório antes de importar

A importação nunca deve gravar direto sem preview.

O botão de preview deve mostrar:

- status da conexão;
- tabelas encontradas;
- tabelas selecionadas para importação;
- quantidade de clientes encontrados;
- quantidade de produtos/peças encontrados;
- quantidade de ordens de serviço encontradas;
- campos mapeados;
- campos ignorados;
- registros inválidos;
- duplicados prováveis;
- exemplos de 5 a 10 registros de cada tipo.

O preview deve usar modo:

```python
dry_run=True
```

E não pode gravar nada no MySQL.

---

# 6. Commit da importação

Só importar de verdade quando o admin clicar em confirmar.

O commit deve usar algo equivalente a:

```python
commit=True
```

Durante o commit:

- criar clientes;
- criar produtos/peças, se o Zokyo tiver módulo de estoque;
- criar ordens de serviço, se o mapeamento for seguro;
- pular registros inválidos;
- registrar erros;
- evitar duplicados;
- gerar log final da importação.

Se algum tipo de dado não puder ser importado com segurança, não force. Mostre no relatório.

---

# 7. Mapeamento esperado CPlus → Zokyo

Use o schema real do `.fdb`, não nomes inventados.

Tente mapear os dados abaixo.

## Clientes

Mapear para o cliente do Zokyo:

- nome;
- CPF;
- CNPJ;
- telefone;
- CEP;
- endereço;
- número da casa;
- cidade;
- UF.

Regras:

- CPF deve ficar apenas com números;
- CNPJ deve ficar apenas com números;
- telefone deve ficar limpo/padronizado;
- se CPF/CNPJ estiver vazio, o cliente ainda pode ser importado;
- se endereço e número estiverem juntos no CPlus, tente separar com segurança;
- se não for seguro separar, importe endereço completo e registre limitação.

## Produtos / peças / estoque

Mapear quando houver:

- código;
- nome;
- categoria;
- quantidade;
- custo;
- preço de venda;
- unidade;
- observações.

## Ordens de Serviço

Mapear quando houver:

- cliente;
- equipamento;
- tipo de equipamento;
- marca;
- modelo;
- número de série;
- defeito alegado;
- defeito encontrado;
- solução/reparo;
- acessórios;
- observações;
- status;
- data de entrada;
- data de saída;
- valor;
- técnico, se houver.

Se o banco CPlus não tiver OS de forma clara, não invente. Apenas documente que não foi possível mapear com segurança.

---

# 8. Regras de duplicidade

Não duplicar dados.

## Cliente

Considerar duplicado se:

- CPF igual e não vazio;
- CNPJ igual e não vazio;
- se não tiver documento, comparar nome + telefone;
- se ainda estiver incerto, marcar como duplicado provável no preview.

## Produto/peça

Considerar duplicado se:

- código igual e não vazio;
- se não tiver código, comparar nome.

## Ordem de Serviço

Considerar duplicado provável se houver combinação semelhante de:

- cliente;
- data de entrada;
- equipamento;
- defeito alegado.

No preview, mostrar esses casos antes de importar.

---

# 9. Log de importação

Criar log técnico da importação.

O log deve conter:

- data/hora;
- usuário admin que executou;
- banco importado;
- quantidade de clientes criados;
- quantidade de clientes ignorados;
- quantidade de produtos criados;
- quantidade de produtos ignorados;
- quantidade de OS criadas;
- quantidade de OS ignoradas;
- erros encontrados;
- registros problemáticos.

Não registrar senha Firebird.

---

# 10. Alterações no cadastro de cliente

Implementar estas mudanças no cadastro de cliente do Zokyo.

## Remover e-mail

Remover campo de e-mail do cadastro, edição e listagem de clientes.

Atenção:

- não remover e-mail do login;
- não remover e-mail de usuários;
- não remover e-mail de fornecedores, se existir;
- não remover e-mail das configurações da empresa, se existir.

A remoção é apenas para cliente.

Se a coluna `email` já existir no banco, não apagar automaticamente. Apenas parar de usar na interface e nas regras.

## Adicionar número da casa

Adicionar campo:

```txt
numero_casa
```

Esse campo é opcional.

## Adicionar CPF/CNPJ inteligente

Trocar ou adaptar o campo de documento do cliente para:

```txt
CPF/CNPJ
```

Regras:

- vazio é permitido;
- até 11 dígitos, formatar como CPF;
- acima de 11 dígitos, formatar como CNPJ;
- máximo 14 dígitos;
- se tiver 11 dígitos, validar CPF;
- se tiver 14 dígitos, validar CNPJ;
- se tiver quantidade diferente de 0, 11 ou 14, mostrar erro;
- CPF/CNPJ inválido não pode limpar o formulário.

Campos opcionais do cliente:

- CPF/CNPJ;
- telefone;
- CEP;
- endereço;
- número da casa;
- cidade;
- UF.

O nome continua obrigatório.

---

# 11. Model e serialização de Cliente

Atualizar o model de cliente conforme a estrutura real do projeto.

Objetivo:

```python
nome = db.Column(db.String(150), nullable=False)
cpf = db.Column(db.String(11), index=True, nullable=True)
cnpj = db.Column(db.String(14), index=True, nullable=True)
telefone = db.Column(db.String(20), nullable=True)
cep = db.Column(db.String(8), nullable=True)
endereco = db.Column(db.String(300), nullable=True)
numero_casa = db.Column(db.String(20), nullable=True)
cidade = db.Column(db.String(100), nullable=True)
uf = db.Column(db.String(2), nullable=True)
```

Se o projeto já usa outros nomes, adapte sem quebrar compatibilidade.

Atualizar `to_dict()` ou serialização equivalente para retornar:

- id;
- nome;
- cpf;
- cnpj;
- documento;
- telefone;
- cep;
- endereco;
- numero_casa;
- cidade;
- uf.

O campo `documento` deve ser CPF formatado se houver CPF, ou CNPJ formatado se houver CNPJ.

---

# 12. Máscara e validação CPF/CNPJ

Atualizar arquivos JS de máscaras/validação existentes.

Criar suporte para:

```html
class="mask-cpf-cnpj"
```

e, se houver validação por classe:

```html
class="validate-cpf-cnpj"
```

Comportamento da máscara:

Entrada:

```txt
12345678901
```

Saída:

```txt
123.456.789-01
```

Entrada:

```txt
12345678000199
```

Saída:

```txt
12.345.678/0001-99
```

Validação:

- vazio é válido, se o campo não for obrigatório;
- 11 dígitos valida CPF;
- 14 dígitos valida CNPJ;
- outro tamanho é inválido;
- CPF/CNPJ inválido mostra erro no campo;
- não apagar dados do formulário.

---

# 13. Migração segura do banco MySQL

Criar script idempotente:

```txt
scripts/migrate_clientes_cpf_cnpj_numero.py
```

Ele deve:

- adicionar coluna `cnpj` se não existir;
- adicionar coluna `numero_casa` se não existir;
- não apagar coluna `email`;
- não apagar dados;
- poder rodar várias vezes;
- imprimir no terminal o que foi feito.

Se necessário, criar também SQL auxiliar em:

```txt
database/migrations/
```

---

# 14. Melhorar erros de formulário

Quando ocorrer erro em:

- cadastro de cliente;
- edição de cliente;
- criação de OS;
- edição de OS;
- cliente rápido dentro da OS;

o sistema deve:

- permanecer na mesma tela;
- manter dados preenchidos;
- destacar campo errado;
- mostrar mensagem clara;
- não fazer redirect limpando tudo.

Evitar este padrão em erro de validação:

```python
flash("Erro")
return redirect(...)
```

Usar renderização da mesma tela com:

```python
form_data
form_errors
```

Ou resposta JSON clara em endpoints AJAX.

---

# 15. Cliente rápido dentro da OS

Na tela de criação de OS, permitir criar cliente sem sair da tela.

O cliente rápido deve ter:

- nome obrigatório;
- CPF/CNPJ opcional;
- telefone opcional;
- CEP opcional;
- endereço opcional;
- número da casa opcional;
- cidade opcional;
- UF opcional.

Não pedir e-mail.

Após criar o cliente rápido:

- selecionar automaticamente o cliente na OS;
- manter os dados já digitados na OS;
- não limpar a tela;
- se houver erro, mostrar no campo exato.

Endpoint sugerido:

```txt
POST /api/clientes/quick-create
```

Resposta de sucesso:

```json
{
  "success": true,
  "cliente": {
    "id": 1,
    "nome": "Cliente Exemplo",
    "cpf": "",
    "cnpj": "",
    "documento": "",
    "telefone": ""
  }
}
```

Resposta de erro:

```json
{
  "success": false,
  "field": "cpf_cnpj",
  "message": "CPF inválido."
}
```

---

# 16. Criar módulo de coleta / PWA

Implementar PWA para o Zokyo.

Criar:

```txt
app/static/manifest.webmanifest
app/static/service-worker.js
app/static/img/icons/
```

Registrar no template base.

O app deve ser instalável no celular.

Cachear apenas:

- CSS;
- JS;
- imagens;
- manifest;
- fontes, se existirem.

Não cachear:

- clientes;
- OS;
- financeiro;
- documentos;
- PDFs;
- uploads;
- APIs privadas;
- dados sensíveis.

Criar ou adaptar uma tela de coleta mobile para abertura rápida de OS.

Pode ser:

```txt
/coleta
```

ou a própria tela de nova OS, desde que fique realmente usável no celular.

A tela precisa ser mobile-first:

- campos grandes;
- botões grandes;
- layout em cards;
- sem tabela larga;
- fluxo rápido para balcão/recepção;
- desktop continua funcionando.

---

# 17. Busca/listagem de clientes

Atualizar a tela de clientes.

Remover coluna:

- e-mail.

Adicionar ou ajustar:

- CPF/CNPJ;
- número da casa, se fizer sentido visual.

A busca deve encontrar cliente por:

- nome;
- CPF;
- CNPJ;
- telefone.

---

# 18. Segurança

Não quebrar autenticação.

Não quebrar permissões.

Importação CPlus apenas para admin.

Não cachear dados sensíveis no PWA.

Não salvar senha Firebird em log.

Não sobrescrever dados sem confirmação.

Não apagar dados existentes.

Não remover e-mail de usuários/login.

Não expor rotas administrativas para usuário comum.

---

# 19. Critérios de aceite

A implementação só está pronta se:

## Cliente

1. Criar cliente apenas com nome funciona.
2. Criar cliente sem e-mail funciona.
3. Cliente não mostra mais campo e-mail.
4. CPF vazio é aceito.
5. CNPJ vazio é aceito.
6. Telefone vazio é aceito.
7. Endereço vazio é aceito.
8. Número da casa vazio é aceito.
9. CPF válido funciona.
10. CNPJ válido funciona.
11. CPF inválido mostra erro e mantém formulário.
12. CNPJ inválido mostra erro e mantém formulário.
13. CPF/CNPJ formata automaticamente.
14. Busca por nome funciona.
15. Busca por CPF funciona.
16. Busca por CNPJ funciona.
17. Busca por telefone funciona.

## Ordem de Serviço

18. Criar OS funciona.
19. Erro na OS não limpa formulário.
20. Erro na OS destaca campo errado.
21. Cliente rápido funciona dentro da OS.
22. Erro no cliente rápido não limpa os dados da OS.
23. Cliente rápido criado fica selecionado automaticamente.

## PWA/coleta

24. Manifest carrega.
25. Service worker registra.
26. App pode ser instalado.
27. Apenas assets seguros são cacheados.
28. Dados sensíveis não são cacheados.
29. Tela de coleta/nova OS é boa no celular.

## CPlus/Firebird

30. Banco `.fdb` real é analisado antes da importação ser codada.
31. Schema real do `.fdb` é documentado.
32. Tabelas reais são detectadas.
33. Nenhum nome de tabela é inventado sem confirmação.
34. Preview funciona antes de importar.
35. Commit só ocorre após confirmação.
36. Clientes são importados sem duplicar CPF/CNPJ.
37. Produtos são importados sem duplicar código.
38. OS só é importada se o mapeamento for seguro.
39. Importador não salva senha.
40. Importador só abre para admin.
41. Sistema continua funcionando mesmo sem Firebird instalado.

## Geral

42. Login continua funcionando.
43. Usuários continuam usando e-mail.
44. Dashboard continua funcionando.
45. Rotas antigas continuam funcionando.
46. Nenhuma tela principal quebra.

---

# 20. Entrega final

Ao final, entregue:

1. resumo do que foi alterado;
2. lista de arquivos criados;
3. lista de arquivos modificados;
4. relatório do schema encontrado no `.fdb`;
5. mapeamento CPlus → Zokyo;
6. tabelas reais usadas na importação;
7. campos reais usados na importação;
8. campos ignorados e motivo;
9. comandos para instalar dependências;
10. comando para rodar migração;
11. como testar cadastro de cliente;
12. como testar criação de OS;
13. como testar PWA;
14. como testar importação CPlus;
15. limitações encontradas.

Se o schema do banco CPlus não permitir importar alguma coisa com segurança, diga claramente. Não invente mapeamento falso.
