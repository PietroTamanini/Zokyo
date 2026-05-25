# app/ - Guia Tecnico da Aplicacao Flask

Este diretorio contem o pacote principal da aplicacao Zokyo. A aplicacao segue o padrao application factory (`create_app`) e organiza dominio, rotas, templates, assets e utilitarios em camadas separadas.

## Responsabilidades

```text
app/
|-- __init__.py          # factory Flask, middlewares, headers, filtros e blueprints
|-- extensions.py        # extensoes compartilhadas, atualmente SQLAlchemy
|-- models/              # entidades e regras persistidas
|-- routes/              # blueprints HTML e API
|-- utils/               # servicos auxiliares e regras transversais
|-- templates/           # templates Jinja2
`-- static/              # CSS e JavaScript
```

## Ciclo de Inicializacao

1. `app.py` chama `create_app(FLASK_ENV)`.
2. `config.py` carrega `.env` e seleciona configuracao.
3. `db.init_app(app)` registra o SQLAlchemy.
4. Context processors injetam usuario atual, configuracao, CSRF e nonce CSP.
5. Middlewares `before_request` aplicam nonce, CSRF, sessao, usuario ativo e primeiro acesso.
6. Blueprints sao registrados.
7. `db.create_all()` garante a criacao das tabelas existentes.
8. APScheduler agenda limpeza de registros antigos de rate limit.

## Fluxo de Request

```text
Nginx -> Gunicorn -> Flask
  -> before_request
     -> CSP nonce
     -> CSRF
     -> normalizacao de sessao
     -> timeout de inatividade
     -> validacao de usuario ativo
     -> primeiro acesso
  -> blueprint/rota
  -> after_request
     -> headers de seguranca
```

## Models

| Arquivo | Tabela | Papel |
| --- | --- | --- |
| `usuario.py` | `usuarios` | usuarios, senha, perfil e status |
| `cliente.py` | `clientes` | cadastro de clientes |
| `fornecedor.py` | `fornecedores` | cadastro de fornecedores |
| `peca.py` | `pecas` | estoque, custo, margem e fornecedor |
| `ordem_servico.py` | `ordens_servico` | OS, equipamento, defeitos, valores, status |
| `os_historico.py` | `os_historico` | historico de mudancas de status |
| `transacao.py` | `transacoes` | financeiro, receitas e despesas |
| `configuracao.py` | `configuracoes` | empresa, metas, PDF, WhatsApp e segredos criptografados |
| `evento_log.py` | `eventos_log` | auditoria |
| `defeito_padrao.py` | `defeitos_padrao` | base de sintomas, causas e solucoes |

## Rotas HTML

| Rota | Blueprint | Descricao |
| --- | --- | --- |
| `/` | `pages` | dashboard |
| `/login` | `auth` | autenticacao |
| `/primeiro-acesso` | `auth` | criacao do primeiro administrador |
| `/os` | `pages` | lista de OS |
| `/os/nova` | `pages` | abertura de OS |
| `/os/<id>` | `pages` | detalhe da OS |
| `/clientes` | `pages` | clientes |
| `/estoque` | `pages` | pecas e estoque |
| `/fornecedores` | `pages` | fornecedores |
| `/financeiro` | `pages` | financeiro |
| `/usuarios` | `usuarios` | gestao de usuarios |
| `/configuracoes` | `configuracoes` | dados da empresa, metas e WhatsApp |
| `/logs` | `logs` | auditoria |

## APIs

As APIs seguem o padrao `/api/<recurso>` e retornam JSON:

- `/api/clientes`
- `/api/fornecedores`
- `/api/pecas`
- `/api/os`
- `/api/transacoes`
- `/api/usuarios`
- `/api/defeitos`
- `/api/logs`
- `/api/whatsapp/status`
- `/api/whatsapp/qr`
- `/api/whatsapp/reconectar`
- `/api/whatsapp/teste`

Requisicoes `POST`, `PUT`, `PATCH` e `DELETE` exigem CSRF.

## Controle de Acesso

Decorators principais:

```python
from app.utils.auth import api_login_required, nivel_required, page_nivel_required

@api_login_required
def rota_api_autenticada():
    ...

@nivel_required("admin", "financeiro")
def rota_api_restrita():
    ...

@page_nivel_required("admin")
def pagina_admin():
    ...
```

Perfis usados pelo sistema:

| Perfil | Uso esperado |
| --- | --- |
| `admin` | acesso administrativo completo |
| `operacional` | rotina de OS e atendimento |
| `financeiro` | financeiro e indicadores financeiros |
| `cadastro` | cadastros operacionais |
| `consulta` | uso de leitura/consulta |

Observacao: algumas APIs legadas usam `tecnico` em decorators de pecas. Se esse perfil nao for exibido no cadastro de usuarios, padronize antes de ampliar permissoes.

## CSRF

Templates HTML:

```html
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
```

JavaScript:

- `app/static/js/api.js` injeta `X-CSRFToken` automaticamente;
- chamadas manuais devem ler `meta[name="csrf-token"]`.

## CSP e Scripts

Scripts inline precisam de nonce:

```html
<script nonce="{{ csp_nonce }}">
  // codigo permitido
</script>
```

Scripts externos devem estar em `app/static/js/` sempre que possivel.

## Frontend

O CSS foi modularizado com `app/static/css/zokyo.css` como entrypoint:

```text
static/css/
|-- zokyo.css
|-- settings/
|-- base/
|-- layout/
|-- components/
`-- utilities/
```

Principais convencoes:

- `layout/` para shell, sidebar e topbar;
- `components/` para botoes, cards, tabelas, modais, paginas, OS e configuracoes;
- `utilities/` para grids, helpers, responsivo e classes pequenas.

JavaScript:

```text
static/js/
|-- api.js
|-- masks.js
|-- ui.js
`-- pages/
```

Arquivos em `pages/` devem conter somente comportamento especifico da pagina.

## PDFs

`app/utils/pdf_gen.py` gera PDF da OS.

Fluxo:

1. valida caminho do `wkhtmltopdf`;
2. renderiza `templates/os_pdf.html`;
3. gera PDF com `pdfkit`;
4. em caso de falha, usa fallback com `ReportLab`.

## WhatsApp

`app/utils/whatsapp.py` isola o envio de mensagens.

Principais protecoes:

- normalizacao de numero;
- fallback para `wa.me`;
- validacao da URL do servidor WPP;
- timeout curto;
- `allow_redirects=False`;
- header `X-Wpp-Token` quando `WPP_SECRET` esta configurado.

## Logs e Auditoria

`EventoLog` registra eventos relevantes por usuario, modulo, operacao e data. A tela `/logs` e restrita a administradores.

## Boas Praticas para Manutencao

- manter regra de negocio em routes/utils/models, nao em templates;
- evitar estilos inline, exceto valores dinamicos inevitaveis;
- usar `api.js` para chamadas autenticadas;
- atualizar `README.md` e este arquivo quando criar modulo novo;
- validar templates antes de entregar alteracoes grandes:

```bash
python - <<'PY'
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
root = Path("app/templates")
env = Environment(loader=FileSystemLoader(str(root)))
for path in root.rglob("*.html"):
    env.parse(path.read_text(encoding="utf-8"))
print("Templates OK")
PY
```
