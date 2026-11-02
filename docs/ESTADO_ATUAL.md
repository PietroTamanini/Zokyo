# Estado atual do Zokyo

Atualizado em **2026-11-02** após a estabilização da suíte e revisão da documentação.

## Validação técnica

- **334 testes Python aprovados** com `.venv\Scripts\python.exe -m pytest -q`.
- `compileall` aprovado para aplicação, migrations e `wsgi.py`.
- `git diff --check` aprovado; os avisos restantes são apenas conversões de CRLF do Git.
- Migration atual: **`20261102_0038` (head)**.
- `flask --app wsgi:app db upgrade` e `flask --app wsgi:app db check` executados com sucesso no banco local.
- A aplicação possui escopo multiempresa, autenticação, RBAC, 2FA, auditoria, rate limit, portal público, landing por empresa, caixa e inventário físico.

## Ambiente local validado

- Painel Flask: `http://127.0.0.1:8000`.
- Site público: `http://127.0.0.1:5500`.
- Banco local: MySQL/MariaDB em `127.0.0.1:3306` quando o XAMPP/MariaDB está ativo.
- Redis é opcional no desenvolvimento e recomendado para sessões e rate limit distribuído.
- Docker permanece suportado pela documentação, mas não é requisito para o fluxo local validado nesta máquina.

## Pendências técnicas conhecidas

1. `flask db check` pode apontar divergências em instalações MySQL antigas que foram criadas antes das migrations de caixa, inventário e landing. É necessário comparar o schema real e aplicar uma migration de reconciliação específica antes do go-live.
2. O fluxo de produção ainda depende de HTTPS, DNS, segredos externos, SMTP, alertas, storage privado, Redis distribuído e homologação das integrações.
3. A unicidade atual é de **uma landing por empresa**, com domínio base, subdomínio e domínio customizado associados à mesma configuração.
4. A validação visual automatizada não substitui a revisão humana em aparelhos reais, especialmente dark mode, impressão de PDF, tabelas extensas e formulários longos.

## Auditoria visual atual

Não foi identificado erro visual funcional reproduzível nesta revisão. O detector apontou apenas melhorias de consistência:

- A faixa azul lateral fixa na área do logo (`.logo-area`) pode ser simplificada se a identidade visual for refinada.
- Há tamanhos e cores literais em CSS que ainda não estão centralizados nos tokens do `DESIGN.md`.
- O detector não conseguiu resolver automaticamente o stylesheet carregado via `url_for`; a confirmação final deve ser feita com a aplicação em execução.

Esses pontos são de qualidade visual, não bloqueadores de execução. Antes do go-live, revisar dark mode, mobile real, contraste, impressão de PDF e textos em português com usuários.

## Como reproduzir a validação

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app migrations wsgi.py
.\.venv\Scripts\python.exe -m flask --app wsgi:app db current
.\.venv\Scripts\python.exe -m flask --app wsgi:app db upgrade
```

Consulte [o que falta](../oque_falta.md) para as pendências externas e [go-live](GO_LIVE.md) antes de qualquer publicação.
