# Zokyo — Sistema de Gestão para Assistência Técnica

Aplicação web para operação de uma assistência técnica de informática, com foco em ordens de serviço, atendimento ao cliente, estoque, financeiro, auditoria, emissão de PDF e comunicação por WhatsApp.

O projeto combina backend Flask, banco MySQL/MariaDB, frontend server-rendered com Jinja2, CSS modularizado e um servidor Node.js opcional para envio automático de mensagens via WhatsApp Web.

## Sumário

- [Visão Geral](#visão-geral)
- [Stack](#stack)
- [Funcionalidades](#funcionalidades)
- [Requisitos](#requisitos)
- [Instalação Local](#instalação-local)
- [Configuração](#configuração)
- [Execução](#execução)
- [Primeiro Acesso](#primeiro-acesso)
- [WhatsApp](#whatsapp)
- [PDF](#pdf)
- [Segurança](#segurança)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Deploy](#deploy)
- [Validação e Manutenção](#validação-e-manutenção)

## Visão Geral

O Zokyo centraliza a rotina operacional de uma assistência técnica:

- cadastro e histórico de clientes;
- abertura, edição, status e histórico de ordens de serviço;
- controle de peças, fornecedores e estoque crítico;
- receitas, despesas, fluxo de caixa e baixas de pagamento;
- dashboard com indicadores operacionais e financeiros;
- usuários com perfis de acesso;
- logs de auditoria;
- geração de PDF da OS;
- integração opcional com WhatsApp.

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | Python 3.11+, Flask 3.x |
| ORM | SQLAlchemy 2.x, Flask-SQLAlchemy |
| Banco | MySQL/MariaDB via PyMySQL |
| Templates | Jinja2 |
| Frontend | HTML, CSS modular, JavaScript vanilla |
| PDF | wkhtmltopdf via pdfkit, fallback ReportLab |
| WhatsApp | Node.js, Express, WPPConnect |
| WSGI | Gunicorn |
| Proxy | Nginx |
| Segurança | CSRF, CSP com nonce, headers HTTP, rate limiting, RBAC |

## Funcionalidades

| Módulo | Recursos principais |
| --- | --- |
| Dashboard | resumo financeiro, OS em aberto, estoque crítico, pipeline de status |
| Ordens de Serviço | criação, edição, peças, financeiro, status, histórico, PDF e WhatsApp |
| Clientes | cadastro, filtros, status ativo/inativo e vínculo com OS |
| Estoque | peças, custo, preço de venda, fornecedor, estoque mínimo e movimentação |
| Fornecedores | cadastro, edição, filtros e status |
| Financeiro | receitas, despesas, pendências, baixa, resumo por período |
| Usuários | perfis, ativação, troca de senha e administração |
| Configurações | empresa, metas, alertas, PDF e WhatsApp |
| Logs | auditoria por usuário, módulo, operação e período |

## Requisitos

Obrigatórios:

- Python 3.11 ou superior;
- MySQL ou MariaDB;
- `pip` e ambiente virtual Python;
- variáveis de ambiente configuradas em `.env`.

Opcionais:

- Node.js 18+ para envio automático de WhatsApp;
- wkhtmltopdf para PDF com layout HTML completo;
- Gunicorn e Nginx para produção Linux.

## Instalação Local

```bash
cd Zokyo
python -m venv venv
```

Ativar ambiente no Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source venv/bin/activate
```

Instalar dependências Python:

```bash
pip install -r requirements.txt
```

Criar banco:

```sql
CREATE DATABASE zokyo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zokyo'@'localhost' IDENTIFIED BY 'troque-esta-senha';
GRANT ALL PRIVILEGES ON zokyo.* TO 'zokyo'@'localhost';
FLUSH PRIVILEGES;
```

Copiar variáveis de ambiente:

```bash
cp .env.example .env
```

No Windows, copie manualmente `.env.example` para `.env`.

## Configuração

Variáveis essenciais:

```env
SECRET_KEY=gere_um_valor_seguro
DATABASE_URL=mysql+pymysql://zokyo:senha@localhost:3306/zokyo
FLASK_ENV=development
```

Gerar `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Variáveis opcionais:

```env
WKHTMLTOPDF_PATH=/usr/bin/wkhtmltopdf
REPORTS_UPLOAD_FOLDER=
REPORTS_PUBLIC_VERIFICATION=true
WPP_SERVER_URL=http://127.0.0.1:3333
WPP_SECRET=segredo_compartilhado
GUNICORN_WORKERS=4
PROXY_COUNT=1
```

Em produção, `SECRET_KEY` e `DATABASE_URL` são obrigatórios. A aplicação recusa iniciar se estiverem ausentes ou com valores placeholder.

Nunca versionar `.env`.

## Execução

Desenvolvimento:

```bash
python app.py
```

Acesse:

```
http://127.0.0.1:5000
```

Produção com Gunicorn:

```bash
FLASK_ENV=production gunicorn -c gunicorn.conf.py wsgi:app
```

## Primeiro Acesso

Ao iniciar com o banco vazio, o sistema redireciona para:

```
/primeiro-acesso
```

Nesse fluxo é criado o primeiro usuário administrador. Depois disso, o login normal acontece em `/login`.

## WhatsApp

O sistema possui dois modos:

| Modo | Descrição |
| --- | --- |
| Manual | gera link `wa.me` com mensagem pronta para o atendente enviar |
| Automático | usa `wpp-server.js` rodando em Node.js para enviar pela sessão WhatsApp Web |

Para o modo automático:

```bash
npm install
WPP_SECRET=segredo_compartilhado node wpp-server.js
```

Configure no `.env` do Flask:

```env
WPP_SERVER_URL=http://127.0.0.1:3333
WPP_SECRET=segredo_compartilhado
```

Detalhes em [wpp-server.README.md](wpp-server.README.md).

## PDF

A geração de PDF usa `wkhtmltopdf` quando instalado e com caminho válido. O sistema detecta automaticamente os caminhos comuns (`/usr/bin/wkhtmltopdf`, `/usr/local/bin/wkhtmltopdf`, `/snap/bin/wkhtmltopdf`) ou usa o valor de `WKHTMLTOPDF_PATH`. Em caso de falha ou ausência, usa fallback com ReportLab.

O caminho também pode ser configurado pelo painel em Configurações.

## Segurança

O sistema inclui:

- CSRF para métodos mutantes;
- CSP com nonce por request (sem `unsafe-inline` em scripts);
- headers HTTP de segurança via `after_request`;
- HSTS em produção;
- timeout de sessão absoluto (8h) e por inatividade (30 min);
- validação de usuário ativo a cada request;
- política de senha forte;
- rate limiting de login persistido no banco, com limpeza agendada via APScheduler;
- ProxyFix configurável via `PROXY_COUNT` para evitar IP spoofing;
- validação de URL do WhatsApp para reduzir risco de SSRF;
- criptografia de segredos de configuração via Fernet (`cryptography`);
- configurações hardened de Gunicorn e Nginx;
- lock de mutex para serializar o endpoint de primeiro acesso.

## Estrutura do Projeto

```
.
├── app.py
├── config.py
├── requirements.txt
├── package.json
├── wpp-server.js
├── wpp-server.README.md
├── gunicorn.conf.py
├── nginx.conf
├── scripts/
│   ├── backup_database.py
│   ├── migrate_constraints.py
│   └── README.md
└── app/
    ├── __init__.py
    ├── extensions.py
    ├── config/
    │   └── branding.py
    ├── models/
    ├── routes/
    ├── utils/
    ├── templates/
    └── static/
```

Documentação técnica interna em [app/README.md](app/README.md).

## Deploy

Fluxo recomendado:

1. provisionar servidor Linux;
2. instalar Python, MySQL/MariaDB, Nginx e dependências;
3. configurar `.env` com `FLASK_ENV=production`;
4. criar banco e usuário dedicado;
5. instalar dependências Python;
6. executar `python scripts/migrate_constraints.py` após o primeiro `python app.py` (aplica índices e constraints);
7. iniciar Gunicorn com `gunicorn.conf.py`;
8. publicar Nginx usando `nginx.conf` como base;
9. configurar HTTPS;
10. opcionalmente iniciar `wpp-server.js` com PM2 ou systemd.

Exemplo de service systemd:

```ini
[Unit]
Description=Zokyo Flask App
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/zokyo
EnvironmentFile=/var/www/zokyo/.env
ExecStart=/var/www/zokyo/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

## Validação e Manutenção

Validar sintaxe Python:

```bash
python -m compileall app
```

Validar Nginx:

```bash
sudo nginx -t
```

Backup versionado:

```bash
python scripts/backup_database.py --output-dir backups --keep-days 14
```

Migrar tabelas de laudos:

```bash
python scripts/migrate_laudos.py
```

Migrar com Flask-Migrate/Alembic:

```bash
python -m flask --app wsgi:app db upgrade
```

Executar testes:

```bash
python -m pytest -q
```

## Importacao CPlus, Clientes CPF/CNPJ e PWA

Dependencias Firebird:

```bash
pip install -r requirements.txt
```

Para importar banco CPlus `.fdb`, a maquina precisa ter Firebird Client/Server
compativel com o arquivo. O banco real analisado em `Banco cplus/CPlus.FDB` usa
ODS 11.1 e foi aberto com Firebird 2.5 Embedded. Se a DLL nativa nao estiver no
PATH, configure:

```env
FIREBIRD_CLIENT_LIBRARY=C:\caminho\para\fbclient.dll
```

Migracao segura de clientes:

```bash
python scripts/migrate_clientes_cpf_cnpj_numero.py
```

Relatorio real do schema CPlus:

```bash
python scripts/analyze_cplus_schema.py "Banco cplus/CPlus.FDB"
```

Importacao CPlus:

1. Entre como admin.
2. Acesse `/importacao/cplus`.
3. Informe caminho do `.fdb`, usuario, senha e charset.
4. Teste conexao.
5. Gere preview.
6. Confirme importacao somente depois de revisar duplicados, invalidos e limitacoes.

A senha Firebird nao e salva em banco, sessao ou log. O commit grava log tecnico
em `instance/import_logs`.

PWA e coleta:

- manifest: `/static/manifest.webmanifest`;
- service worker: `/service-worker.js`;
- agenda de coleta: `/coleta`;
- conclusao mobile: clique em `Concluir no celular` na coleta agendada;
- a agenda grava apenas dados do cliente/local;
- a conclusao cria a OS com dados do equipamento, defeito e fotos;
- fotos ficam em `instance/uploads/os_fotos` e sao acessadas apenas por usuario logado;
- cache restrito a CSS, JS, imagens, fontes e manifest;
- APIs, clientes, OS, financeiro, PDFs, uploads e documentos nao sao cacheados.

Fluxo recomendado:

1. Em `/coleta`, cadastre nome, telefone, documento opcional, endereco e horario.
2. A pessoa no celular abre `/coleta` e entra em `Concluir no celular`.
3. No local, preenche equipamento, marca, modelo, defeito e anexa fotos.
4. Ao salvar, o sistema cria a OS, vincula a coleta e mostra as fotos na tela da OS.

Detalhes, cron e restauração em [scripts/README.md](scripts/README.md). Em produção, mantenha cópia externa dos backups e teste restauração periodicamente.
