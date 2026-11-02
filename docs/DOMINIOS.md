# Domínios personalizados — Zokyo

Estado revisado em 2026-11-02. Cada empresa possui uma configuração de landing (`TenantSite`) e pode usar subdomínio da plataforma ou domínio customizado validado.

## Objetivo

Cada assistência pode ter um domínio próprio em **além** dos subdomínios gratuitos
do Zokyo (`alpha.zokyo.app.br`, `beta.zokyo.app.br`, etc.).

Exemplos:

- `www.respawn.tec.br`
- `www.assistenciaalpha.com.br`

## Infraestrutura reutilizada

| Componente | Arquivo | Uso |
|---|---|---|
| Cloudflare API | `app/services/tenant_provisioning.py` (`sync_tenant_dns`, `_upsert_cloudflare_record`, `_record_type`) | Provisionamento/verificação de DNS via API |
| Nginx | `nginx.docker.conf` | Proxy reverso → `zokyo_app` (TLS final na borda/Cloudflare) |
| Docker | `Dockerfile`, `docker-compose*.yml` | Implantação |

> **Importante:** cadastrar um domínio no banco **não** significa que o domínio
> já está operacional. A ativação depende da verificação de DNS e do proxy TLS.

## Fluxo implementado

1. **Cadastro** (`TenantSite.custom_domain`, via `POST /configuracoes/site/`):
   - Unicidade validada cross-tenant (`validate_unique_domain`).
   - Após troca, `custom_domain_validated = False` e status DNS `pending`.
2. **Verificação** (`POST /configuracoes/site/verify` → `verify_custom_domain`):
   - Consulta registro DNS no Cloudflare (`verify_tenant_domain`).
   - Sucesso → `custom_domain_validated = True`, `dns_status = active`.
   - Falha → mantém `pending` / `error`.
3. **Resolução pública** (`app/services/domain_resolution.py`):
   - Domínio customizado do site (validado) → resolve tenant.
   - Domínio customizado da organização → resolve tenant.
   - Subdomínio sobre `TENANT_BASE_DOMAIN` → resolve tenant.
4. **Indicador** (`get_domain_status`): `none | pending | active | error`.

## Segurança

- Resolução **nunca** aceita domínio customizado não validado.
- Domínio duplicado entre tenants é rejeitado.
- Consultas públicas continuam restritas ao tenant do host resolvido.

## Testes

- `tests/test_tenant_domain_management.py`
- `tests/test_tenant_sites.py` (resolução e duplicidade)

## Comandos

```bash
# Verificacao manual (sem Cloudflare configurado)
TENANT_DNS_MODE=manual python -m ... 
```
