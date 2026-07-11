#!/usr/bin/env python3
"""Migra tabelas do modulo de laudos.

Idempotente e compativel com o padrao atual do projeto. Em uma futura migracao
para Flask-Migrate/Alembic, este script deve virar uma revision formal.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


def table_exists(inspector, name):
    return name in inspector.get_table_names()


def run_safe(conn, sql, desc):
    try:
        conn.execute(text(sql))
        print(f"OK  {desc}")
    except Exception as exc:
        err = str(exc).lower()
        if "already exists" in err or "duplicate" in err or "1050" in err or "1061" in err:
            print(f"SKIP {desc}")
        else:
            print(f"WARN {desc}: {exc}")


def migrate():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        with db.engine.connect() as conn:
            if not table_exists(inspector, "laudo_counters"):
                run_safe(conn, """
                    CREATE TABLE laudo_counters (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        organization_id INT NOT NULL DEFAULT 1,
                        ano INT NOT NULL,
                        proximo_numero INT NOT NULL DEFAULT 1,
                        atualizado_em DATETIME NOT NULL,
                        CONSTRAINT uq_laudo_counter_org_ano UNIQUE (organization_id, ano)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """, "tabela laudo_counters")

            if not table_exists(inspector, "laudos_tecnicos"):
                run_safe(conn, """
                    CREATE TABLE laudos_tecnicos (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        public_uuid VARCHAR(36) NOT NULL UNIQUE,
                        organization_id INT NOT NULL DEFAULT 1,
                        os_id INT NOT NULL,
                        cliente_id INT NOT NULL,
                        equipamento_id INT NULL,
                        tipo VARCHAR(30) NOT NULL DEFAULT 'diagnostico',
                        numero VARCHAR(30) NULL,
                        ano INT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'draft',
                        emitido_em DATETIME NULL,
                        analisado_em DATETIME NULL,
                        tecnico_responsavel_id INT NULL,
                        tecnico_responsavel_nome VARCHAR(120) NULL,
                        criado_por_id INT NOT NULL,
                        atualizado_por_id INT NULL,
                        versao INT NOT NULL DEFAULT 1,
                        laudo_origem_id INT NULL,
                        defeito_relatado TEXT NULL,
                        inspecao_visual TEXT NULL,
                        testes_realizados TEXT NULL,
                        instrumentos_metodos TEXT NULL,
                        medicoes TEXT NULL,
                        diagnostico_tecnico TEXT NULL,
                        causa_provavel TEXT NULL,
                        servicos_realizados TEXT NULL,
                        pecas_utilizadas TEXT NULL,
                        conclusao_tecnica TEXT NULL,
                        estado_final VARCHAR(120) NULL,
                        recomendacoes TEXT NULL,
                        riscos_limitacoes TEXT NULL,
                        garantia VARCHAR(200) NULL,
                        observacoes TEXT NULL,
                        motivo_cancelamento TEXT NULL,
                        empresa_snapshot JSON NULL,
                        cliente_snapshot JSON NULL,
                        equipamento_snapshot JSON NULL,
                        tecnico_snapshot JSON NULL,
                        assinatura_tecnico_nome VARCHAR(120) NULL,
                        assinatura_tecnico_em DATETIME NULL,
                        assinatura_tecnico_metodo VARCHAR(50) NULL,
                        assinatura_cliente_nome VARCHAR(120) NULL,
                        assinatura_cliente_em DATETIME NULL,
                        assinatura_cliente_metodo VARCHAR(50) NULL,
                        criado_em DATETIME NOT NULL,
                        atualizado_em DATETIME NOT NULL,
                        finalizado_em DATETIME NULL,
                        cancelado_em DATETIME NULL,
                        pdf_path VARCHAR(600) NULL,
                        pdf_sha256 VARCHAR(64) NULL,
                        pdf_gerado_em DATETIME NULL,
                        pdf_template_version VARCHAR(30) NULL,
                        verification_token VARCHAR(80) NULL UNIQUE,
                        verificacao_publica BOOLEAN NOT NULL DEFAULT TRUE,
                        CONSTRAINT uq_laudo_org_numero UNIQUE (organization_id, numero),
                        CONSTRAINT fk_laudo_os FOREIGN KEY (os_id) REFERENCES ordens_servico(id),
                        CONSTRAINT fk_laudo_cliente FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                        CONSTRAINT fk_laudo_criador FOREIGN KEY (criado_por_id) REFERENCES usuarios(id),
                        CONSTRAINT fk_laudo_tecnico FOREIGN KEY (tecnico_responsavel_id) REFERENCES usuarios(id),
                        CONSTRAINT fk_laudo_origem FOREIGN KEY (laudo_origem_id) REFERENCES laudos_tecnicos(id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """, "tabela laudos_tecnicos")

            if not table_exists(inspector, "laudo_fotos"):
                run_safe(conn, """
                    CREATE TABLE laudo_fotos (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        laudo_id INT NOT NULL,
                        tipo VARCHAR(30) NOT NULL,
                        legenda VARCHAR(255) NULL,
                        ordem INT NOT NULL DEFAULT 0,
                        nome_original VARCHAR(255) NULL,
                        storage_key VARCHAR(600) NOT NULL,
                        mime_type VARCHAR(100) NOT NULL,
                        tamanho_bytes INT NOT NULL,
                        largura INT NULL,
                        altura INT NULL,
                        sha256 VARCHAR(64) NOT NULL,
                        usuario_id INT NOT NULL,
                        criado_em DATETIME NOT NULL,
                        CONSTRAINT fk_laudo_foto_laudo FOREIGN KEY (laudo_id) REFERENCES laudos_tecnicos(id),
                        CONSTRAINT fk_laudo_foto_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """, "tabela laudo_fotos")

            if not table_exists(inspector, "laudo_eventos"):
                run_safe(conn, """
                    CREATE TABLE laudo_eventos (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        laudo_id INT NOT NULL,
                        usuario_id INT NULL,
                        tipo VARCHAR(30) NOT NULL,
                        descricao TEXT NULL,
                        dados JSON NULL,
                        criado_em DATETIME NOT NULL,
                        CONSTRAINT fk_laudo_evento_laudo FOREIGN KEY (laudo_id) REFERENCES laudos_tecnicos(id),
                        CONSTRAINT fk_laudo_evento_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """, "tabela laudo_eventos")

            for sql, desc in [
                ("CREATE INDEX ix_laudos_os_id ON laudos_tecnicos(os_id)", "idx laudos os"),
                ("CREATE INDEX ix_laudos_cliente_id ON laudos_tecnicos(cliente_id)", "idx laudos cliente"),
                ("CREATE INDEX ix_laudos_status ON laudos_tecnicos(status)", "idx laudos status"),
                ("CREATE INDEX ix_laudos_emitido_em ON laudos_tecnicos(emitido_em)", "idx laudos emissao"),
                ("CREATE INDEX ix_laudo_fotos_laudo_tipo ON laudo_fotos(laudo_id, tipo)", "idx laudo fotos"),
                ("CREATE INDEX ix_laudo_eventos_laudo ON laudo_eventos(laudo_id, criado_em)", "idx laudo eventos"),
            ]:
                run_safe(conn, sql, desc)
            conn.commit()
        print("Migracao de laudos concluida.")


if __name__ == "__main__":
    migrate()
