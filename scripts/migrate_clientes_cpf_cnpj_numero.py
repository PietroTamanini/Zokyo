#!/usr/bin/env python3
"""
Migra clientes para CPF/CNPJ inteligente e numero da casa.

Idempotente: pode rodar varias vezes. Nao remove nem altera dados de email.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, inspect, text

from config import Config


def _database_uri():
    return os.environ.get("DATABASE_URL") or Config.SQLALCHEMY_DATABASE_URI


def _columns(inspector):
    return {col["name"] for col in inspector.get_columns("clientes")}


def _indexes(inspector):
    return {idx["name"] for idx in inspector.get_indexes("clientes")}


def _run(conn, sql, label):
    conn.execute(text(sql))
    print(f"[ok] {label}")


def _digits(value):
    return re.sub(r"\D", "", value or "")


def _normalize_documents(conn):
    rows = conn.execute(text("SELECT id, cpf, cnpj FROM clientes")).mappings().all()
    invalid = []

    for row in rows:
        cpf = _digits(row.get("cpf"))
        cnpj = _digits(row.get("cnpj"))

        if cnpj and len(cnpj) != 14:
            invalid.append((row["id"], "cnpj", row.get("cnpj")))
            continue

        if cpf and len(cpf) == 14 and not cnpj:
            cnpj = cpf
            cpf = ""
        elif cpf and len(cpf) != 11:
            invalid.append((row["id"], "cpf", row.get("cpf")))
            continue

        conn.execute(
            text("UPDATE clientes SET cpf = :cpf, cnpj = :cnpj WHERE id = :id"),
            {
                "id": row["id"],
                "cpf": cpf or None,
                "cnpj": cnpj or None,
            },
        )

    if invalid:
        print("[erro] documentos invalidos impedem reduzir o tamanho das colunas:")
        for cliente_id, field, value in invalid[:20]:
            print(f"  cliente {cliente_id}: {field}={value!r}")
        if len(invalid) > 20:
            print(f"  ... e mais {len(invalid) - 20} registros")
        raise SystemExit(1)

    print("[ok] documentos existentes normalizados sem truncamento")


def migrate():
    engine = create_engine(_database_uri(), pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        if "clientes" not in inspector.get_table_names():
            raise SystemExit("[erro] tabela clientes nao existe. Inicialize o banco antes da migracao.")

        cols = _columns(inspector)

        with engine.begin() as conn:
            if "cnpj" not in cols:
                _run(conn, "ALTER TABLE clientes ADD COLUMN cnpj VARCHAR(14) NULL", "coluna clientes.cnpj adicionada")
            else:
                print("[skip] coluna clientes.cnpj ja existe")

            if "numero_casa" not in cols:
                _run(conn, "ALTER TABLE clientes ADD COLUMN numero_casa VARCHAR(20) NULL", "coluna clientes.numero_casa adicionada")
            else:
                print("[skip] coluna clientes.numero_casa ja existe")

            _normalize_documents(conn)

            _run(conn, "ALTER TABLE clientes MODIFY nome VARCHAR(150) NOT NULL", "clientes.nome VARCHAR(150)")
            _run(conn, "ALTER TABLE clientes MODIFY cpf VARCHAR(11) NULL", "clientes.cpf VARCHAR(11)")
            _run(conn, "ALTER TABLE clientes MODIFY telefone VARCHAR(20) NULL", "clientes.telefone VARCHAR(20)")
            _run(conn, "ALTER TABLE clientes MODIFY cep VARCHAR(8) NULL", "clientes.cep VARCHAR(8)")
            _run(conn, "ALTER TABLE clientes MODIFY endereco VARCHAR(300) NULL", "clientes.endereco VARCHAR(300)")
            _run(conn, "ALTER TABLE clientes MODIFY cidade VARCHAR(100) NULL", "clientes.cidade VARCHAR(100)")
            _run(conn, "ALTER TABLE clientes MODIFY uf VARCHAR(2) NULL", "clientes.uf VARCHAR(2)")

        inspector = inspect(engine)
        idxs = _indexes(inspector)
        with engine.begin() as conn:
            if "ix_clientes_cnpj" not in idxs:
                _run(conn, "CREATE INDEX ix_clientes_cnpj ON clientes(cnpj)", "indice ix_clientes_cnpj criado")
            else:
                print("[skip] indice ix_clientes_cnpj ja existe")

            if "ix_clientes_cpf" not in idxs:
                _run(conn, "CREATE INDEX ix_clientes_cpf ON clientes(cpf)", "indice ix_clientes_cpf criado")
            else:
                print("[skip] indice ix_clientes_cpf ja existe")

        print("[done] migracao de clientes concluida sem apagar dados")
    finally:
        engine.dispose()


if __name__ == "__main__":
    migrate()
