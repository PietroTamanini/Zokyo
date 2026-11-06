# Admin global, domínios e subdomínios

O primeiro acesso cria um admin global sem empresa. Esse usuario entra em `/platform` e gerencia empresas, planos, assinaturas, DNS e admins de cada empresa sem acessar dados internos dos tenants.

## Estrutura modular

- `app/routes/platform.py`: somente rotas HTTP e compatibilidade dos endpoints `platform.*`.
- `app/admin/security.py`: autorizacao do admin global e senhas temporarias.
- `app/admin/dashboard.py`: consultas agregadas, KPIs, DNS e contexto da tela.
- `app/admin/organizations.py`: criacao/edicao de empresas, admins de tenant, reset de senha e DNS.
- `app/admin/plans.py`: planos, assinatura sandbox e JSON de planos.
- `app/templates/admin/`: tela do admin global separada por partials.
- `app/static/css/components/admin.css`: estilos do admin global e telas administrativas.

## Desenvolvimento local

No ambiente local, use o modo `wildcard` apenas para dizer ao Zokyo que os
subdomínios de teste serão aceitos. Isso não cria DNS público:

```env
TENANT_BASE_DOMAIN=zokyo.localhost
TENANT_DNS_MODE=wildcard
```

No provedor de DNS, crie:

```text
Tipo: A ou CNAME
Nome: *
Valor: IP ou hostname publico do servidor
Proxy: ativado se usar Cloudflare e o proxy for desejado
```

Com isso, uma empresa criada no painel responde em
`slug.zokyo.localhost`. O navegador normalmente resolve `*.localhost` para a
própria máquina; se necessário, adicione os nomes ao arquivo `hosts`.

## Produção com DNS manual

Em produção, use o modo `manual` quando você mesmo criará os registros DNS:

```env
TENANT_BASE_DOMAIN=zokyo.com.br
TENANT_DNS_MODE=manual
```

No provedor DNS, crie um wildcard `*` apontando para o proxy/servidor do
Zokyo, ou crie um registro individual para cada empresa. O Zokyo não chama a
API DNS e exibirá o status como `manual`; isso é esperado nesse modo. O proxy
reverso ainda precisa aceitar os hosts e o HTTPS precisa estar configurado.

O modo `wildcard` também pode ser usado em produção somente se o wildcard DNS
já estiver configurado e você aceitar que o Zokyo marque os subdomínios como
ativos sem verificar cada registro. Ele não substitui o registro DNS nem o
certificado HTTPS.

### Domínio próprio da empresa

Na criação da empresa, preencha o domínio próprio, por exemplo
`painel.assistencia.com.br`. O subdomínio `slug.zokyo.com.br` continua como
endereço alternativo. No provedor DNS da empresa, crie um registro `A` para o
IP do servidor ou `CNAME` para o hostname do proxy. Depois configure HTTPS no
proxy reverso (Cloudflare é uma opção simples) e encaminhe o `Host` original
para o Zokyo.

Para desenvolvimento local, use `TENANT_BASE_DOMAIN=zokyo.localhost`; assim
`empresa.zokyo.localhost` aponta para a própria máquina em navegadores que
resolvem `localhost`. Outra opção é adicionar os nomes ao arquivo `hosts`:

```text
127.0.0.1 empresa.zokyo.localhost
127.0.0.1 outra.zokyo.localhost
```

Não é necessário criar registros DNS públicos para testar empresas localmente.

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
- Senha inicial: se ficar vazia, o sistema gera uma senha temporaria forte e mostra no aviso de sucesso.
- Plano e status: podem ser alterados na tabela de empresas.
- Empresa inativa: bloqueia login daquele tenant.
- `past_due`, `suspended` e `cancelled`: bloqueiam novas escritas do tenant.
- Admin de empresa: pode ser criado ou ter senha resetada no painel global.
- Funcionarios: o dono/admin da empresa gerencia em `/usuarios`, incluindo permissoes extras e negadas.
