# DJ Tech site público

Site estático para `https://djtechinfo.com.br/` com consulta pública de OS em `/os`.

## Estrutura

- `index.html`: clone local do site institucional atual da DJ Tech, com link para consulta de OS.
- `os/index.html`: consulta de ordem de serviço por número + CPF/CNPJ.
- `css/style.css`, `js/main.js` e `img/`: arquivos espelhados do site atual.
- `assets/css/os-consulta.css`: acabamento visual da página de consulta.
- `assets/js/config.js`: define a base da API pública.
- `assets/js/os-consulta.js`: integra com `POST /api/public/os-consulta` no mesmo domínio.
- `server.py`: servidor local com proxy para o Zokyo em `127.0.0.1:8000`.
- `robots.txt` e `sitemap.xml`: arquivos para indexação do domínio principal.
- `Dockerfile`: imagem do site público para rodar junto com o Zokyo via Compose.

## Local

Rode o servidor local com proxy:

```powershell
cd dj-tech
python server.py
```

Depois acesse:

- `http://127.0.0.1:5500/`
- `http://127.0.0.1:5500/os/`

Em localhost, o site fica em `127.0.0.1:5500` e o `server.py` repassa somente `/api/public/*` para o Zokyo em `127.0.0.1:8000`. A URL da consulta continua no domínio principal.

## Docker local

Na raiz do Zokyo, suba banco, painel e site público juntos:

```powershell
docker compose up --build
```

Depois acesse:

- Site público da DJ Tech: `http://127.0.0.1:5500/`
- Consulta de OS no domínio público local: `http://127.0.0.1:5500/os/`
- Painel Zokyo: `http://127.0.0.1:8000/`

No Docker, o site usa `PANEL_API=http://app:8000` por dentro da rede do Compose. O navegador não vê essa URL interna.

## Produção

Quando publicar:

- `djtechinfo.com.br` aponta para esta pasta/site público.
- O sistema administrativo pode ficar em um subdomínio separado, mas o site público não mostra botão ou link para ele.
- No servidor do domínio principal, configure proxy reverso para repassar apenas `/api/public/*` ao Zokyo.
- No Zokyo, deixe `DJTECH_SITE_ORIGINS` contendo:

```text
https://djtechinfo.com.br,https://www.djtechinfo.com.br
```

O arquivo `assets/js/config.js` deixa `apiBase` vazio de propósito. Assim, a consulta em `https://djtechinfo.com.br/os` chama `https://djtechinfo.com.br/api/public/os-consulta`, sem mandar o cliente para outro domínio.

Exemplo de proxy Nginx no domínio principal:

```nginx
location /api/public/ {
    proxy_pass https://SEU_HOST_DO_ZOKYO/api/public/;
    proxy_set_header Host SEU_HOST_DO_ZOKYO;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```
