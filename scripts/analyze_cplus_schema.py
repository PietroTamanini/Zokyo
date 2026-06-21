#!/usr/bin/env python3
"""Gera relatorios de schema do CPlus Firebird."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cplus_firebird_importer import CPlusFirebirdImporter, FirebirdCredentials


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "Banco cplus/CPlus.FDB"
    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)

    importer = CPlusFirebirdImporter(FirebirdCredentials(
        database_path=db_path,
        user=os.environ.get("CPLUS_FB_USER", "SYSDBA"),
        password=os.environ.get("CPLUS_FB_PASSWORD", "masterkey"),
        charset=os.environ.get("CPLUS_FB_CHARSET", "WIN1252"),
    ))
    schema = importer.inspect_schema()
    selected_tables = [
        t for t in (
            "CLIENTE", "PRODUTO", "PRODUTOESTOQUE", "PRODUTOPRECO", "SECAO",
            "OS_ORDEMSERVICO", "OS_STATUS", "OS_TECNICO", "OS_PRODSERV",
        )
        if t in schema["tables"]
    ]
    counts = {
        "clientes": importer._scalar("SELECT COUNT(*) FROM CLIENTE") if "CLIENTE" in schema["tables"] else 0,
        "produtos": importer._scalar("SELECT COUNT(*) FROM PRODUTO") if "PRODUTO" in schema["tables"] else 0,
        "ordens_servico": importer._scalar("SELECT COUNT(*) FROM OS_ORDEMSERVICO") if "OS_ORDEMSERVICO" in schema["tables"] else 0,
    }

    (out_dir / "cplus_schema_full.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    detected = schema["detected_entities"]
    lines = [
        "# Relatorio tecnico CPlus Firebird",
        "",
        f"Arquivo analisado: `{db_path}`",
        f"Total de tabelas reais encontradas: {schema['table_count']}",
        "",
        "## Tabelas encontradas",
        "",
    ]
    for table in sorted(schema["tables"]):
        lines.append(f"- `{table}`")

    lines.extend([
        "",
        "## Entidades provaveis",
        "",
        f"- Clientes: {', '.join(detected['clientes']) or 'nenhuma'}",
        f"- Auxiliares de clientes: {', '.join(detected['clientes_auxiliares']) or 'nenhuma'}",
        f"- Produtos/estoque: {', '.join(detected['produtos']) or 'nenhuma'}",
        f"- Ordens de servico: {', '.join(detected['ordens_servico']) or 'nenhuma'}",
        "",
        "## Tabelas usadas na importacao",
        "",
        "- `CLIENTE` para clientes.",
        "- `PRODUTO`, `PRODUTOESTOQUE`, `PRODUTOPRECO`, `SECAO` para pecas/estoque.",
        "- `OS_ORDEMSERVICO`, `OS_STATUS`, `OS_TECNICO`, `OS_PRODSERV` para OS.",
        "",
        "## Mapeamento CPlus -> Zokyo",
        "",
    ])
    for group, mapping in importer.mapping_report().items():
        lines.append(f"### {group}")
        for src, dest in mapping.items():
            lines.append(f"- `{src}` -> `{dest}`")
        lines.append("")

    lines.extend([
        "## Campos ignorados e motivo",
        "",
    ])
    for group, ignored in importer.ignored_fields_report().items():
        lines.append(f"### {group}")
        for item in ignored:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend([
        "## Tratamentos aplicados",
        "",
        "- CPF/CNPJ sao importados apenas com digitos e validados quando presentes.",
        "- Telefone e CEP sao limpos para digitos.",
        "- `CLIENTE.ENDERECO` e separado em endereco/numero apenas quando ha padrao seguro.",
        "- Status de OS e normalizado para os status do Zokyo por palavras-chave.",
        "- Duplicidade de cliente: CPF, CNPJ ou nome + telefone.",
        "- Duplicidade de produto: codigo ou nome.",
        "- Duplicidade provavel de OS: cliente + data + equipamento + defeito.",
        "",
        "## Dados sem importacao segura sem confirmacao",
        "",
    ])
    for item in importer.manual_confirmation_report():
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Preview gerado",
        "",
        f"- Clientes encontrados: {counts['clientes']}",
        f"- Produtos encontrados: {counts['produtos']}",
        f"- OS encontradas: {counts['ordens_servico']}",
        f"- Tabelas selecionadas: {', '.join(selected_tables)}",
        "",
        "## Schema detalhado das tabelas usadas",
        "",
    ])
    for table in selected_tables:
        meta = schema["tables"].get(table)
        if not meta:
            continue
        lines.append(f"### {table}")
        lines.append(f"- PK: {', '.join(meta['primary_key']) or 'nenhuma'}")
        if meta["foreign_keys"]:
            lines.append("- FKs:")
            for fk in meta["foreign_keys"]:
                lines.append(f"  - `{fk['field']}` -> `{fk['ref_table']}.{fk['ref_field']}`")
        lines.append("- Colunas:")
        for col in meta["columns"]:
            null = "NULL" if col["nullable"] else "NOT NULL"
            lines.append(f"  - `{col['name']}` {col['type']} {null}")
        lines.append("")

    lines.append("O schema completo, incluindo colunas/chaves de todas as tabelas, esta em `docs/cplus_schema_full.json`.")
    (out_dir / "cplus_schema_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Relatorios gerados em docs/cplus_schema_report.md e docs/cplus_schema_full.json")


if __name__ == "__main__":
    main()
