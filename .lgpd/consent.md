# Consentimento no protótipo — 2026-11-06

## Implementado

- `consent_records` registra uma decisão por finalidade, cliente e empresa. A migration `0048` adiciona versão do aviso e referência da evidência, e bloqueia UPDATE/DELETE comuns por triggers no MariaDB e SQLite. A proteção não impede um administrador do banco de remover os triggers ou restaurar um backup antigo.
- O serviço `register_consent` aceita uma concessão apenas com origem de coleta direta (`portal` ou `public_form`), versão identificável do aviso e referência da evidência. Revogações criam um novo registro; `has_active_consent` considera a decisão mais recente e exige metadados para reconhecer uma concessão.
- A ficha de privacidade exibe histórico e metadados. Foi retirada a opção de conceder consentimento manualmente. A exportação técnica inclui os registros e seus metadados.
- Registros anteriores à migration ficam com versão e evidência desconhecidas. A migração não presume nem cria consentimento retroativo.

## Antes de usar consentimento como base de uma finalidade opcional

1. Definir e aprovar a finalidade, o texto do aviso, sua versão e o responsável pelo tratamento de cada fluxo. O projeto ainda é um protótipo; não existe aviso publicado como vigente.
2. Criar a coleta direta no ponto de interação do titular, com escolha separada por finalidade, registro verificável da ação e mecanismo de revogação acessível.
3. Associar o registro ao cliente correto sem depender apenas de nome ou e-mail informado, proteger a referência da evidência e testar duplicações e isolamento entre empresas.
4. Verificar `has_active_consent` antes de cada tratamento opcional que realmente dependa dessa base, inclusive jobs e integrações. Hoje nenhum fluxo de marketing está conectado a essa checagem.
5. Testar revogação, exportação, recuperação de backup e retenção dos registros sob uma política aprovada.

Este documento descreve controles técnicos locais; não declara que o protótipo está adequado à LGPD ou pronto para operar com dados reais.
