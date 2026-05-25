#!/usr/bin/env python3
"""
scripts/migrate_constraints.py
--------------------------------
Aplica melhorias de integridade e índices ao banco de dados.

Execute APÓS fazer backup do banco:
    python scripts/migrate_constraints.py

O script é idempotente — pode ser executado múltiplas vezes com segurança.
"""
import sys
import os

# Garante import do app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.extensions import db
from sqlalchemy import text, inspect


def run_safe(conn, sql: str, desc: str):
    """Executa SQL ignorando erros de 'já existe'."""
    try:
        conn.execute(text(sql))
        print(f"  ✅ {desc}")
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "already exists" in err or "1061" in err:
            print(f"  ⏭  {desc} (já aplicado)")
        else:
            print(f"  ⚠️  {desc}: {e}")


def migrate():
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)

        with db.engine.connect() as conn:
            print("\n── Índices na tabela clientes ──────────────────────────")

            # Índice em cpf (busca e unicidade lógica)
            run_safe(conn,
                "CREATE INDEX ix_clientes_cpf ON clientes(cpf)",
                "Índice ix_clientes_cpf")

            # Índice em email
            run_safe(conn,
                "CREATE INDEX ix_clientes_email ON clientes(email)",
                "Índice ix_clientes_email")

            print("\n── Ajustes de tamanho em clientes ──────────────────────")

            # CPF: só dígitos = máx 11 chars
            run_safe(conn,
                "ALTER TABLE clientes MODIFY cpf VARCHAR(11)",
                "cpf VARCHAR(11)")

            # Telefone: só dígitos = máx 15 chars
            run_safe(conn,
                "ALTER TABLE clientes MODIFY telefone VARCHAR(15)",
                "telefone VARCHAR(15)")

            # Email: RFC 5321 = máx 254
            run_safe(conn,
                "ALTER TABLE clientes MODIFY email VARCHAR(254)",
                "email VARCHAR(254)")

            print("\n── Índices na tabela fornecedores ──────────────────────")

            run_safe(conn,
                "CREATE INDEX ix_fornecedores_cnpj ON fornecedores(cnpj)",
                "Índice ix_fornecedores_cnpj")

            run_safe(conn,
                "CREATE INDEX ix_fornecedores_email ON fornecedores(email)",
                "Índice ix_fornecedores_email")

            print("\n── Ajustes de tamanho em fornecedores ──────────────────")

            run_safe(conn,
                "ALTER TABLE fornecedores MODIFY cnpj VARCHAR(14)",
                "cnpj VARCHAR(14)")

            run_safe(conn,
                "ALTER TABLE fornecedores MODIFY telefone VARCHAR(15)",
                "telefone VARCHAR(15)")

            run_safe(conn,
                "ALTER TABLE fornecedores MODIFY email VARCHAR(254)",
                "email VARCHAR(254)")

            print("\n── Índices na tabela usuarios ──────────────────────────")

            # Email já tem UNIQUE no modelo — confirma
            run_safe(conn,
                "CREATE UNIQUE INDEX ix_usuarios_email ON usuarios(email)",
                "Índice único ix_usuarios_email")

            print("\n── Índices na tabela ordens_servico ────────────────────")

            run_safe(conn,
                "CREATE INDEX ix_os_cliente_id ON ordens_servico(cliente_id)",
                "Índice ix_os_cliente_id")

            run_safe(conn,
                "CREATE INDEX ix_os_status ON ordens_servico(status)",
                "Índice ix_os_status")

            run_safe(conn,
                "CREATE INDEX ix_os_data_entrada ON ordens_servico(data_entrada)",
                "Índice ix_os_data_entrada")

            run_safe(conn,
                "CREATE INDEX ix_os_deletado_em ON ordens_servico(deletado_em)",
                "Índice ix_os_deletado_em")

            print("\n── Índices na tabela transacoes ────────────────────────")

            run_safe(conn,
                "CREATE INDEX ix_transacoes_tipo ON transacoes(tipo)",
                "Índice ix_transacoes_tipo")

            run_safe(conn,
                "CREATE INDEX ix_transacoes_status ON transacoes(status)",
                "Índice ix_transacoes_status")

            run_safe(conn,
                "CREATE INDEX ix_transacoes_criado_em ON transacoes(criado_em)",
                "Índice ix_transacoes_criado_em")

            run_safe(conn,
                "CREATE INDEX ix_transacoes_os_id ON transacoes(os_id)",
                "Índice ix_transacoes_os_id")

            conn.commit()

        print("\n✅ Migração concluída!\n")


if __name__ == "__main__":
    migrate()
