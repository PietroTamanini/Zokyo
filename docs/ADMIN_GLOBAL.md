# Admin global e subdominios

O primeiro acesso cria um admin global sem empresa. Esse usuario entra em `/platform` e gerencia empresas, planos, assinaturas, DNS e admins de cada empresa sem acessar dados internos dos tenants.

## Subdominio automatico

O caminho mais simples para `empresa.tamanini.dev.br` e usar wildcard DNS:

```env
TENANT_BASE_DOMAIN=tamanini.dev.br
TENANT_DNS_MODE=wildcard
```

No provedor de DNS, crie:

```text
Tipo: A ou CNAME
Nome: *
Valor: IP ou hostname publico do servidor
Proxy: ativado se usar Cloudflare e o proxy for desejado
```

Com isso, toda empresa criada no painel ja responde em `slug.tamanini.dev.br`, desde que o Nginx/proxy envie esses hosts para o Zokyo.

## Cloudflare API

Use quando quiser criar um registro DNS por empresa:

```env
TENANT_DNS_MODE=cloudflare
TENANT_DNS_TARGET=IP_OU_HOST_DO_SERVIDOR
CLOUDFLARE_ZONE_ID=ZONE_ID
CLOUDFLARE_API_TOKEN=TOKEN
```

O token precisa permitir editar DNS da zona `tamanini.dev.br`. No painel da Cloudflare, crie um token com permissao `Zone:DNS:Edit` para essa zona. Depois, ao criar empresa com "Criar/ativar subdominio", o Zokyo chama a API e marca o DNS como `active` se o registro for criado.

## Operacao

- `/platform`: painel global.
- Criar empresa: gera slug automatico pelo nome quando o campo subdominio fica vazio.
- Plano e status: podem ser alterados na tabela de empresas.
- Empresa inativa: bloqueia login daquele tenant.
- `past_due`, `suspended` e `cancelled`: bloqueiam novas escritas do tenant.
- Admin de empresa: pode ser criado ou ter senha resetada no painel global.
- Funcionarios: o dono/admin da empresa gerencia em `/usuarios`, incluindo permissoes extras e negadas.
