# app/ — Guia Técnico da Aplicação Flask

Este diretório contém o pacote principal da aplicação Zokyo. A aplicação segue o padrão application factory (`create_app`) e organiza domínio, rotas, templates, assets e utilitários em camadas separadas.

## Responsabilidades

```
app/
├── __init__.py          # factory Flask, middlewares, headers, filtros e blueprints
├── extensions.py        # extensões compartilhadas (SQLAlchemy)
├── config/
│   └── branding.py      # resolve nome, logo e cores da marca a partir de Configuracao
├── models/              # entidades e regras persistidas
├── routes/              # blueprints HTML e API
├── utils/               # serviços auxiliares e regras transversais
├── templates/           # templates Jinja2
└── static/              # CSS e JavaScript
```

## Ciclo de Inicialização

1. `app.py` chama `create_app(FLASK_ENV)`.
2. `config.py` carrega `.env` e seleciona a configuração (`DevelopmentConfig` ou `ProductionConfig`).
3. `ProductionConfig.init_app` valida `SECRET_KEY` e `DATABASE_URL`; aborta se ausentes ou com placeholder.
4. `db.init_app(app)` registra o SQLAlchemy.
5. Context processors injetam usuário atual, configuração da empresa, CSRF token e nonce CSP.
6. Middlewares `before_request` aplicam: nonce CSP, verificação CSRF, normalização de sessão, timeout de inatividade (30 min), validação de usuário ativo e redirecionamento de primeiro acesso.
7. Blueprints são registrados (ver tabela de rotas abaixo).
8. `db.create_all()` garante a criação das tabelas existentes.
9. APScheduler agenda limpeza de registros antigos de rate limit a cada 24h.

## Fluxo de Request

```
Nginx → Gunicorn → Flask
  → before_request
     → CSP nonce
     → CSRF
     → normalização de sessão
     → timeout de inatividade
     → validação de usuário ativo
     → primeiro acesso
  → blueprint/rota
  → after_request
     → headers de segurança (CSP, HSTS, X-Frame-Options, etc.)
```

## Models

| Arquivo | Tabela | Papel |
| --- | --- | --- |
| `usuario.py` | `usuarios` | usuários, senha, perfil e status |
| `cliente.py` | `clientes` | cadastro de clientes |
| `fornecedor.py` | `fornecedores` | cadastro de fornecedores |
| `peca.py` | `pecas` | estoque, custo, margem e fornecedor |
| `ordem_servico.py` | `ordens_servico` | OS, equipamento, defeitos, valores, status |
| `os_historico.py` | `os_historico` | histórico de mudanças de status |
| `transacao.py` | `transacoes` | financeiro, receitas e despesas |
| `configuracao.py` | `configuracoes` | empresa, metas, PDF, WhatsApp e segredos criptografados |
| `evento_log.py` | `eventos_log` | auditoria |
| `defeito_padrao.py` | `defeitos_padrao` | base de sintomas, causas e soluções |

A tabela de associação `os_pecas` (many-to-many entre `ordens_servico` e `pecas`) também é declarada em `ordem_servico.py`.

## Blueprints Registrados

Os blueprints são todos importados e registrados no factory em `app/__init__.py`. Os blueprints `cfg_bp` e `logs_bp` são importados diretamente dos seus módulos e não estão reexportados em `routes/__init__.py`.

| Blueprint | Módulo | Prefixo |
| --- | --- | --- |
| `auth_bp` | `routes/auth.py` | `/` |
| `pages_bp` | `routes/pages.py` | `/` |
| `clientes_bp` | `routes/clientes.py` | `/api` |
| `os_bp` | `routes/os.py` | `/api` |
| `pecas_bp` | `routes/pecas.py` | `/api` |
| `fornecedores_bp` | `routes/fornecedores.py` | `/api` |
| `transacoes_bp` | `routes/transacoes.py` | `/api` |
| `usuarios_bp` | `routes/usuarios.py` | `/` |
| `defeitos_bp` | `routes/defeitos_padrao.py` | `/api` |
| `cfg_bp` | `routes/configuracoes.py` | `/` |
| `logs_bp` | `routes/logs.py` | `/` |

## Rotas HTML

| Rota | Blueprint | Descrição |
| --- | --- | --- |
| `/` | `pages_bp` | dashboard |
| `/login` | `auth_bp` | autenticação |
| `/primeiro-acesso` | `auth_bp` | criação do primeiro administrador |
| `/os` | `pages_bp` | lista de OS |
| `/os/nova` | `pages_bp` | abertura de OS |
| `/os/<id>` | `pages_bp` | detalhe da OS |
| `/clientes` | `pages_bp` | clientes |
| `/estoque` | `pages_bp` | peças e estoque |
| `/fornecedores` | `pages_bp` | fornecedores |
| `/financeiro` | `pages_bp` | financeiro |
| `/usuarios` | `usuarios_bp` | gestão de usuários |
| `/configuracoes` | `cfg_bp` | dados da empresa, metas e WhatsApp |
| `/logs` | `logs_bp` | auditoria |

## APIs

As APIs seguem o padrão `/api/<recurso>` e retornam JSON:

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

Requisições `POST`, `PUT`, `PATCH` e `DELETE` exigem CSRF.

## Controle de Acesso

Decorators principais definidos em `app/utils/auth.py`:

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

Observação: algumas rotas de peças possuem decorators legados com `tecnico`. Esse perfil não é exibido no cadastro de usuários. Padronize para os perfis acima antes de ampliar permissões.

## CSRF

Templates HTML:

```html
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
```

JavaScript:

- `app/static/js/api.js` injeta `X-CSRFToken` automaticamente em todas as requisições;
- chamadas manuais devem ler `meta[name="csrf-token"]`.

## CSP e Scripts

Scripts inline precisam de nonce:

```html
<script nonce="{{ csp_nonce }}">
  // código permitido
</script>
```

Scripts externos devem estar em `app/static/js/` sempre que possível.

## Branding

`app/config/branding.py` resolve o nome da empresa, logo e cores a partir do modelo `Configuracao`. O resultado é injetado em todos os templates via context processor `inject_branding`.

Não altere valores de marca diretamente nos templates; use o painel de Configurações ou edite `branding.py`.

## Frontend

O CSS foi modularizado com `app/static/css/zokyo.css` como entrypoint:

```
static/css/
├── zokyo.css
├── settings/
├── base/
├── layout/
├── components/
└── utilities/
```

Principais convenções:

- `layout/` para shell, sidebar e topbar;
- `components/` para botões, cards, tabelas, modais, páginas, OS e configurações;
- `utilities/` para grids, helpers, responsivo e classes pequenas.

JavaScript:

```
static/js/
├── api.js        # fetch wrapper com CSRF e tratamento de erro
├── masks.js      # máscaras de input (CPF, CNPJ, telefone, CEP)
├── ui.js         # comportamentos genéricos de UI
├── validators.js # validações de formulário client-side
├── viacep.js     # autocomplete de endereço via ViaCEP
└── pages/        # scripts específicos por página
```

Arquivos em `pages/` devem conter somente comportamento específico da página.

## PDFs

`app/utils/pdf_gen.py` gera PDF da OS.

Fluxo:

1. valida caminho do `wkhtmltopdf` (detecção automática ou `WKHTMLTOPDF_PATH`);
2. renderiza `templates/os_pdf.html`;
3. gera PDF com `pdfkit` (orientação landscape, A4, margens de 8mm);
4. em caso de falha, usa fallback com ReportLab.

## WhatsApp

`app/utils/whatsapp.py` isola o envio de mensagens.

Proteções aplicadas:

- normalização de número;
- fallback para `wa.me`;
- validação da URL do servidor WPP (reduz risco de SSRF);
- timeout curto;
- `allow_redirects=False`;
- header `X-Wpp-Token` quando `WPP_SECRET` está configurado.

## Logs e Auditoria

`EventoLog` registra eventos relevantes por usuário, módulo, operação e data. A função utilitária `registrar` (exportada de `app/models`) é o ponto de entrada para gravar eventos em qualquer rota. A tela `/logs` é restrita a administradores.

## Boas Práticas para Manutenção

- manter regra de negócio em routes/utils/models, não em templates;
- evitar estilos inline, exceto valores dinâmicos inevitáveis;
- usar `api.js` para chamadas autenticadas;
- atualizar `README.md` e este arquivo ao criar módulo novo;
- validar templates antes de entregar alterações grandes:

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
