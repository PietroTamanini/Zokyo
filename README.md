# Zokyo - Sistema de Gestao para Assistencia Tecnica

Aplicacao web para operacao de uma assistencia tecnica de informatica, com foco em ordens de servico, atendimento ao cliente, estoque, financeiro, auditoria, emissao de PDF e comunicacao por WhatsApp.

O projeto combina backend Flask, banco MySQL, frontend server-rendered com Jinja2, CSS modularizado e um servidor Node.js opcional para envio automatico de mensagens via WhatsApp Web.

## Sumario

- [Visao Geral](#visao-geral)
- [Stack](#stack)
- [Funcionalidades](#funcionalidades)
- [Requisitos](#requisitos)
- [Instalacao Local](#instalacao-local)
- [Configuracao](#configuracao)
- [Execucao](#execucao)
- [Primeiro Acesso](#primeiro-acesso)
- [WhatsApp](#whatsapp)
- [PDF](#pdf)
- [Seguranca](#seguranca)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Deploy](#deploy)
- [Validacao e Manutencao](#validacao-e-manutencao)

## Visao Geral

O Zokyo centraliza a rotina operacional de uma assistencia tecnica:

- cadastro e historico de clientes;
- abertura, edicao, status e historico de ordens de servico;
- controle de pecas, fornecedores e estoque critico;
- receitas, despesas, fluxo de caixa e baixas de pagamento;
- dashboard com indicadores operacionais e financeiros;
- usuarios com perfis de acesso;
- logs de auditoria;
- geracao de PDF da OS;
- integracao opcional com WhatsApp.

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
| Seguranca | CSRF, CSP com nonce, headers HTTP, rate limiting, RBAC |

## Funcionalidades

| Modulo | Recursos principais |
| --- | --- |
| Dashboard | resumo financeiro, OS em aberto, estoque critico, pipeline de status |
| Ordens de Servico | criacao, edicao, pecas, financeiro, status, historico, PDF e WhatsApp |
| Clientes | cadastro, filtros, status ativo/inativo e vinculo com OS |
| Estoque | pecas, custo, preco de venda, fornecedor, estoque minimo e movimentacao |
| Fornecedores | cadastro, edicao, filtros e status |
| Financeiro | receitas, despesas, pendencias, baixa, resumo por periodo |
| Usuarios | perfis, ativacao, troca de senha e administracao |
| Configuracoes | empresa, metas, alertas, PDF e WhatsApp |
| Logs | auditoria por usuario, modulo, operacao e periodo |

## Requisitos

Obrigatorios:

- Python 3.11 ou superior;
- MySQL ou MariaDB;
- `pip` e ambiente virtual Python;
- variaveis de ambiente configuradas em `.env`.

Opcionais:

- Node.js 18+ para envio automatico de WhatsApp;
- wkhtmltopdf para PDF com layout HTML completo;
- Gunicorn e Nginx para producao Linux.

## Instalacao Local

```bash
cd zokyo-patched
python -m venv venv
```

Ativar ambiente:

```powershell
.\venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source venv/bin/activate
```

Instalar dependencias:

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

Copiar ambiente:

```bash
cp .env.example .env
```

No Windows, copie manualmente `.env.example` para `.env` se preferir.

## Configuracao

Variaveis essenciais:

```env
SECRET_KEY=gere_um_valor_seguro
DATABASE_URL=mysql+pymysql://zokyo:senha@localhost:3306/zokyo
FLASK_ENV=development
```

Gerar `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Recomendado para producao:

```bash
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Use o resultado em:

```env
ENCRYPTION_SALT=valor_base64_gerado
```

Variaveis opcionais:

```env
WKHTMLTOPDF_PATH=/usr/bin/wkhtmltopdf
WPP_SERVER_URL=http://127.0.0.1:3333
WPP_SECRET=segredo_compartilhado
GUNICORN_WORKERS=4
PROXY_COUNT=1
```

Nunca versionar `.env`.

## Execucao

Desenvolvimento:

```bash
python app.py
```

Acesse:

```text
http://127.0.0.1:5000
```

Producao com Gunicorn:

```bash
FLASK_ENV=production gunicorn -c gunicorn.conf.py app:app
```

Em producao, `SECRET_KEY` e `DATABASE_URL` precisam estar corretamente definidos.

## Primeiro Acesso

Ao iniciar com o banco vazio, o sistema redireciona para:

```text
/primeiro-acesso
```

Nesse fluxo e criado o primeiro usuario administrador. Depois disso, o login normal acontece em `/login`.

## WhatsApp

O sistema possui dois modos:

| Modo | Descricao |
| --- | --- |
| Manual | gera link `wa.me` com mensagem pronta para o atendente enviar |
| Automatico | usa `wpp-server.js` rodando em Node.js para enviar pela sessao WhatsApp Web |

Para o modo automatico:

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

A geracao de PDF usa `wkhtmltopdf`, quando instalado e com caminho valido. Em caso de falha, o sistema usa fallback com `ReportLab`.

Configure o caminho em `WKHTMLTOPDF_PATH` ou no painel em Configuracoes.

## Seguranca

O sistema inclui:

- CSRF para metodos mutantes;
- CSP com nonce por request para scripts inline;
- headers HTTP de seguranca;
- timeout de sessao por inatividade;
- validacao de usuario ativo a cada request;
- politica de senha forte;
- rate limiting de login persistido no banco;
- rate limiting e token no `wpp-server.js`;
- validacao de URL do WhatsApp para reduzir risco de SSRF;
- criptografia de segredos de configuracao via Fernet;
- configuracoes hardened de Gunicorn e Nginx.

Detalhes em [README_SECURITY_FIXES.md](README_SECURITY_FIXES.md).

## Estrutura do Projeto

```text
.
|-- app.py
|-- config.py
|-- requirements.txt
|-- package.json
|-- wpp-server.js
|-- gunicorn.conf.py
|-- nginx.conf
|-- app/
|   |-- __init__.py
|   |-- extensions.py
|   |-- models/
|   |-- routes/
|   |-- utils/
|   |-- templates/
|   `-- static/
```

Documentacao tecnica interna em [app/README.md](app/README.md).

## Deploy

Fluxo recomendado:

1. provisionar servidor Linux;
2. instalar Python, MySQL/MariaDB, Nginx e dependencias;
3. configurar `.env` com `FLASK_ENV=production`;
4. criar banco e usuario dedicado;
5. instalar dependencias Python;
6. iniciar Gunicorn com `gunicorn.conf.py`;
7. publicar Nginx usando `nginx.conf` como base;
8. configurar HTTPS;
9. opcionalmente iniciar `wpp-server.js` com PM2 ou systemd.

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

## Validacao e Manutencao

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

Detalhes, cron e restauracao em [scripts/README.md](scripts/README.md). Em producao, mantenha copia externa dos backups e teste restauracao periodicamente.
