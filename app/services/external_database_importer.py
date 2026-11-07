"""Importação de bancos externos Firebird para o Zokyo."""
from __future__ import annotations

import json
import os
import re
import csv
import sqlite3
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import current_app, g, has_app_context, has_request_context
from sqlalchemy import text

from app.extensions import db
from app.models import Cliente, OrdemServico, OSHistorico, Peca, Transacao, Usuario, proximo_numero_os
from app.utils.blind_index import blind_index
from app.utils.sanitizers import sanitize_cep, sanitize_phone, sanitize_text
from app.utils.validators import validar_cnpj, validar_cpf


class ExternalImportError(RuntimeError):
    """Erro amigável de importação de banco externo."""


@dataclass
class FirebirdCredentials:
    database_path: str
    user: str = "SYSDBA"
    password: str = ""
    charset: str = "WIN1252"
    source_type: str = "firebird"
    host: str = ""
    port: int | None = None
    database: str = ""
    profile: str = "auto"
    delimiter: str = ","
    sheet: str = ""


def _digits(value: Any, limit: int | None = None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:limit] if limit else digits


def _json_safe(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _to_datetime(value: Any):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _type_name(field_type, subtype, length, precision, scale):
    names = {
        7: "SMALLINT",
        8: "INTEGER",
        10: "FLOAT",
        12: "DATE",
        13: "TIME",
        14: "CHAR",
        16: "NUMERIC" if subtype else "BIGINT",
        27: "DOUBLE",
        35: "TIMESTAMP",
        37: "VARCHAR",
        261: "BLOB",
    }
    base = names.get(field_type, f"TYPE_{field_type}")
    if base in {"CHAR", "VARCHAR"}:
        return f"{base}({length})"
    if base == "NUMERIC":
        return f"NUMERIC({precision or 18},{abs(scale or 0)})"
    if base == "BLOB":
        return f"BLOB{subtype or ''}"
    return base


class ExternalFirebirdImporter:
    def __init__(self, credentials: FirebirdCredentials):
        self.credentials = credentials
        self._driver = None

    def _connect(self):
        db_path = Path(self.credentials.database_path)
        if not db_path.exists():
            raise ExternalImportError("Arquivo .fdb não encontrado no servidor.")

        errors = []

        try:
            import fdb

            kwargs = {
                "database": str(db_path),
                "user": self.credentials.user or "SYSDBA",
                "password": self.credentials.password or "",
                "charset": self.credentials.charset or "WIN1252",
            }
            fb_library = os.environ.get("FIREBIRD_CLIENT_LIBRARY", "").strip()
            if fb_library:
                kwargs["fb_library_name"] = fb_library
            self._driver = "fdb"
            return fdb.connect(**kwargs)
        except ImportError as exc:
            errors.append(f"fdb não instalado: {exc}")
        except Exception as exc:
            errors.append(str(exc))

        try:
            from firebird.driver import connect, driver_config

            fb_library = os.environ.get("FIREBIRD_CLIENT_LIBRARY", "").strip()
            if fb_library:
                driver_config.fb_client_library.value = fb_library
            self._driver = "firebird-driver"
            return connect(
                str(db_path),
                user=self.credentials.user or "SYSDBA",
                password=self.credentials.password or "",
                charset=self.credentials.charset or "WIN1252",
            )
        except ImportError as exc:
            errors.append(f"firebird-driver não instalado: {exc}")
        except Exception as exc:
            errors.append(str(exc))

        detail = " | ".join(errors) or "Cliente Firebird indisponível."
        raise ExternalImportError(
            "Não foi possível abrir o Firebird. Instale Firebird Client/Server "
            "compatível com o .fdb ou defina FIREBIRD_CLIENT_LIBRARY. Detalhe: "
            f"{detail}"
        )

    def _rows(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(sql, params)
            columns = [desc[0].strip() for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def _scalar(self, sql: str, params: tuple = ()) -> Any:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else None

    def test_connection(self) -> dict[str, Any]:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT COUNT(*)
                FROM rdb$relations
                WHERE COALESCE(rdb$system_flag, 0) = 0
                  AND rdb$view_blr IS NULL
            """)
            table_count = cur.fetchone()[0]
        return {"success": True, "driver": self._driver, "table_count": table_count}

    def inspect_schema(self) -> dict[str, Any]:
        tables = self._rows("""
            SELECT TRIM(rdb$relation_name) AS table_name
            FROM rdb$relations
            WHERE COALESCE(rdb$system_flag, 0) = 0
              AND rdb$view_blr IS NULL
            ORDER BY rdb$relation_name
        """)
        table_names = [row["TABLE_NAME"] for row in tables]

        schema = {"table_count": len(table_names), "tables": {}}
        for table in table_names:
            cols = self._rows("""
                SELECT TRIM(rf.rdb$field_name) AS field_name,
                       f.rdb$field_type AS field_type,
                       f.rdb$field_sub_type AS field_sub_type,
                       f.rdb$field_length AS field_length,
                       f.rdb$field_precision AS field_precision,
                       f.rdb$field_scale AS field_scale,
                       COALESCE(rf.rdb$null_flag, 0) AS null_flag
                FROM rdb$relation_fields rf
                JOIN rdb$fields f ON f.rdb$field_name = rf.rdb$field_source
                WHERE rf.rdb$relation_name = ?
                ORDER BY rf.rdb$field_position
            """, (table,))
            pks = self._rows("""
                SELECT TRIM(s.rdb$field_name) AS field_name
                FROM rdb$relation_constraints rc
                JOIN rdb$index_segments s ON s.rdb$index_name = rc.rdb$index_name
                WHERE rc.rdb$relation_name = ? AND rc.rdb$constraint_type = 'PRIMARY KEY'
                ORDER BY s.rdb$field_position
            """, (table,))
            fks = self._rows("""
                SELECT TRIM(rc.rdb$constraint_name) AS constraint_name,
                       TRIM(seg.rdb$field_name) AS field_name,
                       TRIM(rc2.rdb$relation_name) AS ref_table,
                       TRIM(seg2.rdb$field_name) AS ref_field
                FROM rdb$relation_constraints rc
                JOIN rdb$ref_constraints refc ON refc.rdb$constraint_name = rc.rdb$constraint_name
                JOIN rdb$relation_constraints rc2 ON rc2.rdb$constraint_name = refc.rdb$const_name_uq
                JOIN rdb$index_segments seg ON seg.rdb$index_name = rc.rdb$index_name
                JOIN rdb$index_segments seg2 ON seg2.rdb$index_name = rc2.rdb$index_name
                    AND seg2.rdb$field_position = seg.rdb$field_position
                WHERE rc.rdb$relation_name = ? AND rc.rdb$constraint_type = 'FOREIGN KEY'
                ORDER BY rc.rdb$constraint_name, seg.rdb$field_position
            """, (table,))
            schema["tables"][table] = {
                "columns": [
                    {
                        "name": c["FIELD_NAME"],
                        "type": _type_name(
                            c["FIELD_TYPE"],
                            c["FIELD_SUB_TYPE"],
                            c["FIELD_LENGTH"],
                            c["FIELD_PRECISION"],
                            c["FIELD_SCALE"],
                        ),
                        "nullable": not bool(c["NULL_FLAG"]),
                    }
                    for c in cols
                ],
                "primary_key": [r["FIELD_NAME"] for r in pks],
                "foreign_keys": [
                    {
                        "name": r["CONSTRAINT_NAME"],
                        "field": r["FIELD_NAME"],
                        "ref_table": r["REF_TABLE"],
                        "ref_field": r["REF_FIELD"],
                    }
                    for r in fks
                ],
            }
        schema["detected_entities"] = self.detect_entities(schema)
        return schema

    def detect_entities(self, schema: dict[str, Any]) -> dict[str, Any]:
        tables = set(schema.get("tables", {}))
        return {
            "clientes": ["CLIENTE"] if "CLIENTE" in tables else [],
            "clientes_auxiliares": [t for t in ("CLIENTEENDERECO", "CONTATOSCLI", "CIDADE", "UF") if t in tables],
            "produtos": [t for t in ("PRODUTO", "PRODUTOESTOQUE", "PRODUTOPRECO", "SECAO", "UNIDADE") if t in tables],
            "ordens_servico": [t for t in ("OS_ORDEMSERVICO", "OS_STATUS", "OS_TECNICO", "OS_PRODSERV") if t in tables],
            "financeiro": [t for t in ("CONTARECEBER", "CONTAPAGAR") if t in tables],
            "compatibilidade": {
                "firebird_assistencia": bool({"CLIENTE", "PRODUTO", "OS_ORDEMSERVICO"} & tables),
                "assistencia_mysql": bool({"clientes", "produtos", "os", "lancamentos"} & tables),
                "ordesk_like": bool({"customers", "orders", "services", "products"} & tables),
                "csv_generico": False,
            },
        }

    def _split_address(self, endereco):
        text = sanitize_text(endereco, max_length=300)
        if not text:
            return None, None, None
        match = re.match(r"^(.*?)[,\s]+(\d+[A-Za-z0-9\-\/]*)$", text)
        if match and len(match.group(1).strip()) >= 3:
            return match.group(1).strip(), match.group(2).strip(), None
        return text, None, "Número da casa não separado com segurança."

    def _map_cliente(self, row):
        cpf = _digits(row.get("CPF"), 11)
        cnpj = _digits(row.get("CNPJ"), 14)
        if cpf and not validar_cpf(cpf):
            cpf = ""
        if cnpj and not validar_cnpj(cnpj):
            cnpj = ""
        endereco, numero, warning = self._split_address(row.get("ENDERECO"))
        return {
            "source_id": str(row.get("CODCLI") or "").strip(),
            "nome": sanitize_text(row.get("NOMECLI"), max_length=150),
            "cpf": cpf or None,
            "cnpj": cnpj or None,
            "telefone": sanitize_phone(row.get("TELEFONE")) or None,
            "email": sanitize_text(row.get("EMAIL"), max_length=254) or None,
            "cep": sanitize_cep(row.get("CEP")) or None,
            "endereco": endereco,
            "numero_casa": numero,
            "cidade": sanitize_text(row.get("CIDADE"), max_length=100) or None,
            "uf": sanitize_text(row.get("ESTADO"), max_length=2).upper() or None,
            "warning": warning,
        }

    def _cliente_duplicate(self, item):
        if item.get("cpf"):
            found = Cliente.query.filter_by(cpf_bidx=blind_index(item["cpf"], "cpf")).first()
            if found:
                return found, "CPF já existe"
        if item.get("cnpj"):
            found = Cliente.query.filter_by(cnpj_bidx=blind_index(item["cnpj"], "cnpj")).first()
            if found:
                return found, "CNPJ já existe"
        if item.get("nome") and item.get("telefone"):
            found = Cliente.query.filter_by(nome=item["nome"], telefone=item["telefone"]).first()
            if found:
                return found, "nome + telefone já existem"
        if item.get("nome") and item.get("endereco"):
            found = Cliente.query.filter(
                db.func.lower(Cliente.nome) == item["nome"].lower(),
                db.func.lower(Cliente.endereco) == item["endereco"].lower(),
            ).first()
            if found:
                return found, "nome + endereço já existem"
        if item.get("nome") and not any(item.get(key) for key in ("cpf", "cnpj", "telefone", "endereco")):
            found = Cliente.query.filter(db.func.lower(Cliente.nome) == item["nome"].lower()).first()
            if found:
                return found, "nome já existe"
        return None, None

    def _cliente_rows(self):
        return self._rows("""
            SELECT CODCLI, NOMECLI, CPF, CNPJ, TELEFONE, EMAIL, CEP, ENDERECO, CIDADE, ESTADO
            FROM CLIENTE
            ORDER BY CODCLI
        """)

    def _produto_rows(self):
        return self._rows("""
            SELECT p.CODPROD, p.CODIGO, p.NOMEPROD, p.UNIDADE, p.PRECUSTO, p.OBS,
                   s.NOMESECAO AS CATEGORIA,
                   COALESCE(SUM(pe.ESTATU), 0) AS QUANTIDADE,
                   MAX(pp.PRECO) AS PRECO
            FROM PRODUTO p
            LEFT JOIN SECAO s ON s.CODSEC = p.CODSEC
            LEFT JOIN PRODUTOESTOQUE pe ON pe.CODPROD = p.CODPROD
            LEFT JOIN PRODUTOPRECO pp ON pp.CODPROD = p.CODPROD
            WHERE COALESCE(p.FLAGINATIVO, 'N') <> 'Y'
            GROUP BY p.CODPROD, p.CODIGO, p.NOMEPROD, p.UNIDADE, p.PRECUSTO, p.OBS, s.NOMESECAO
            ORDER BY p.CODPROD
        """)

    def _map_produto(self, row):
        custo = float(row.get("PRECUSTO") or 0)
        preco = float(row.get("PRECO") or 0)
        margem = round(((preco - custo) / custo) * 100, 2) if custo > 0 and preco > 0 else 0
        return {
            "source_id": str(row.get("CODPROD") or "").strip(),
            "codigo": sanitize_text(row.get("CODIGO"), max_length=100) or None,
            "nome": sanitize_text(row.get("NOMEPROD"), max_length=200),
            "categoria": sanitize_text(row.get("CATEGORIA"), max_length=100) or None,
            "quantidade": int(float(row.get("QUANTIDADE") or 0)),
            "custo": custo,
            "margem": margem,
            "ignored": {
                "UNIDADE": row.get("UNIDADE"),
                "OBS": bool(row.get("OBS")),
            },
        }

    def _produto_duplicate(self, item):
        if item.get("codigo"):
            found = Peca.query.filter_by(codigo=item["codigo"]).first()
            if found:
                return found, "código já existe"
        found = Peca.query.filter_by(nome=item["nome"]).first() if item.get("nome") else None
        if found:
            return found, "nome já existe"
        return None, None

    def _os_rows(self):
        return self._rows("""
            SELECT os.CODOS, os.NUMOS, os.CODCLI, os.EQUIPAMENTO, os.IDENTIFICADOR, os.MARCAMODELO,
                   os.TIPO, os.OCORRENCIA, os.OBS, os.SOLUCAO, os.DATA, os.DATSAI,
                   os.GARANTIA, os.CODSTATUS, os.CODTEC,
                   st.STATUS AS STATUS_NOME,
                   tec.TECNICO AS TECNICO_NOME,
                   COALESCE(SUM(ps.VALORTOTAL), 0) AS VALOR
            FROM OS_ORDEMSERVICO os
            LEFT JOIN OS_STATUS st ON st.CODSTATUS = os.CODSTATUS
            LEFT JOIN OS_TECNICO tec ON tec.CODTEC = os.CODTEC
            LEFT JOIN OS_PRODSERV ps ON ps.CODOS = os.CODOS
            GROUP BY os.CODOS, os.NUMOS, os.CODCLI, os.EQUIPAMENTO, os.IDENTIFICADOR, os.MARCAMODELO,
                     os.TIPO, os.OCORRENCIA, os.OBS, os.SOLUCAO, os.DATA, os.DATSAI,
                     os.GARANTIA, os.CODSTATUS, os.CODTEC, st.STATUS, tec.TECNICO
            ORDER BY os.CODOS
        """)

    def _os_item_rows(self):
        return self._rows("""
            SELECT ps.CODOS, ps.CODPROD, ps.QUANTIDADE, ps.TIPO, ps.VALORUNITARIO,
                   ps.VALORTOTAL, ps.COMPLEMENTO, p.NOMEPROD
            FROM OS_PRODSERV ps
            LEFT JOIN PRODUTO p ON p.CODPROD = ps.CODPROD
            ORDER BY ps.CODOS, ps.CODPRODSERV
        """)

    def _items_by_os(self):
        grouped = {}
        try:
            rows = self._os_item_rows()
        except Exception:
            return grouped
        for row in rows:
            grouped.setdefault(str(row.get("CODOS") or "").strip(), []).append(row)
        return grouped

    def _status_zokyo(self, status_nome):
        s = sanitize_text(status_nome, max_length=60).lower()
        if any(k in s for k in ("entreg", "finaliz", "devolv")):
            return "entregue"
        if "pronto" in s:
            return "pronto"
        if "aprova" in s or "orc" in s:
            return "aguardando_aprovacao"
        if "reparo" in s or "manut" in s:
            return "em_reparo"
        if "avalia" in s or "teste" in s or "anal" in s:
            return "em_analise"
        return "recepcao"

    def _split_marca_modelo(self, value):
        text = sanitize_text(value, max_length=100)
        if not text:
            return None, None
        parts = re.split(r"\s*/\s*|\s+-\s+", text, maxsplit=1)
        if len(parts) == 2:
            return parts[0][:100] or None, parts[1][:100] or None
        return None, text[:100]

    def _map_os(self, row, cliente_by_source):
        marca, modelo = self._split_marca_modelo(row.get("MARCAMODELO"))
        cliente = cliente_by_source.get(str(row.get("CODCLI") or "").strip())
        return {
            "source_id": str(row.get("CODOS") or "").strip(),
            "numero": int(row.get("NUMOS") or 0) or None,
            "cliente": cliente,
            "cliente_source_id": str(row.get("CODCLI") or "").strip(),
            "tipo_aparelho": sanitize_text(row.get("EQUIPAMENTO") or row.get("TIPO"), max_length=100) or None,
            "marca": marca,
            "modelo": modelo,
            "numero_serie": sanitize_text(row.get("IDENTIFICADOR"), max_length=100) or None,
            "defeito_alegado": sanitize_text(row.get("OCORRENCIA"), max_length=5000) or None,
            "solucao": sanitize_text(row.get("SOLUCAO"), max_length=5000) or None,
            "observacoes": sanitize_text(row.get("OBS"), max_length=5000) or None,
            "status": self._status_zokyo(row.get("STATUS_NOME")),
            "data_entrada": _to_datetime(row.get("DATA")),
            "data_saida": _to_datetime(row.get("DATSAI")),
            "valor_servico": float(row.get("VALOR") or 0),
            "garantia_dias": int(row.get("GARANTIA") or 90),
            "tecnico_nome": sanitize_text(row.get("TECNICO_NOME"), max_length=120) or None,
        }

    def _os_duplicate(self, item):
        if not item.get("cliente"):
            return None, "cliente ausente"
        if item.get("numero"):
            found = OrdemServico.query.filter_by(numero=item["numero"]).filter(
                OrdemServico.deletado_em.is_(None)
            ).first()
            if found:
                return found, "número de OS já existe"
        q = OrdemServico.query.filter_by(cliente_id=item["cliente"].id).filter(
            OrdemServico.deletado_em.is_(None)
        )
        if item.get("data_entrada"):
            q = q.filter(OrdemServico.data_entrada == item["data_entrada"])
        if item.get("tipo_aparelho"):
            q = q.filter(OrdemServico.tipo_aparelho == item["tipo_aparelho"])
        if item.get("defeito_alegado"):
            q = q.filter(OrdemServico.defeito_alegado == item["defeito_alegado"])
        found = q.first()
        if found:
            return found, "OS semelhante já existe"
        return None, None

    def _contapagar_rows(self):
        return self._rows("""
            SELECT CODCP, CREDOR, VALOR, DATENTR, DATVENC, ORIGEM, LOCAL, OBS,
                   FLAGPAGO, DATPAG, VALORPG
            FROM CONTAPAGAR
            ORDER BY CODCP
        """)

    def _contareceber_rows(self):
        return self._rows("""
            SELECT CODCR, CODCLI, DEVEDOR, VALOR, DATENTR, DATVENC, ORIGEM, LOCAL, OBS,
                   FLAGPAGO, DATPAG, VALORPG
            FROM CONTARECEBER
            ORDER BY CODCR
        """)

    def _map_financeiro(self, row, tipo: str):
        paid = str(row.get("FLAGPAGO") or "").upper() == "Y"
        source_id = str(row.get("CODCP") or row.get("CODCR") or "").strip()
        descricao = sanitize_text(row.get("ORIGEM") or row.get("CREDOR") or row.get("DEVEDOR"), max_length=240)
        if not descricao:
            descricao = f"Lançamento importado #{source_id}"
        return {
            "source_id": source_id,
            "tipo": tipo,
            "categoria": "fornecedor" if tipo == "despesa" else "servico",
            "descricao": f"{descricao} [origem externa {source_id}]",
            "valor": float(row.get("VALORPG") or row.get("VALOR") or 0),
            "forma_pagamento": sanitize_text(row.get("LOCAL"), max_length=50) or None,
            "status": "pago" if paid else "pendente",
            "data_vencimento": _to_datetime(row.get("DATVENC") or row.get("DATENTR")),
            "data_pagamento": _to_datetime(row.get("DATPAG")) if paid else None,
        }

    def _transacao_duplicate(self, item):
        return Transacao.query.filter_by(
            tipo=item["tipo"],
            descricao=item["descricao"],
            valor=Decimal(str(item["valor"])),
            data_vencimento=item["data_vencimento"],
        ).first()

    def preview(self) -> dict[str, Any]:
        schema = self.inspect_schema()
        tables = set(schema["tables"])
        selected = []
        invalid = {"clientes": [], "produtos": [], "ordens_servico": [], "financeiro": []}
        duplicates = {"clientes": [], "produtos": [], "ordens_servico": [], "financeiro": []}
        examples = {"clientes": [], "produtos": [], "ordens_servico": [], "financeiro": []}

        if "CLIENTE" in tables:
            selected.append("CLIENTE")
            for row in self._cliente_rows():
                item = self._map_cliente(row)
                if not item["nome"]:
                    invalid["clientes"].append({"source_id": item["source_id"], "reason": "nome vazio"})
                    continue
                dup, reason = self._cliente_duplicate(item)
                if dup:
                    duplicates["clientes"].append({"source_id": item["source_id"], "reason": reason, "zokyo_id": dup.id})
                if len(examples["clientes"]) < 10:
                    examples["clientes"].append(item)

        if "PRODUTO" in tables:
            selected.extend([t for t in ("PRODUTO", "PRODUTOESTOQUE", "PRODUTOPRECO", "SECAO") if t in tables])
            for row in self._produto_rows():
                item = self._map_produto(row)
                if not item["nome"]:
                    invalid["produtos"].append({"source_id": item["source_id"], "reason": "nome vazio"})
                    continue
                dup, reason = self._produto_duplicate(item)
                if dup:
                    duplicates["produtos"].append({"source_id": item["source_id"], "reason": reason, "zokyo_id": dup.id})
                if len(examples["produtos"]) < 10:
                    examples["produtos"].append(item)

        if "OS_ORDEMSERVICO" in tables:
            selected.extend([t for t in ("OS_ORDEMSERVICO", "OS_STATUS", "OS_TECNICO", "OS_PRODSERV") if t in tables])
            cliente_by_source = {}
            cliente_name_by_source = {}
            cliente_sources = set()
            for row in self._cliente_rows() if "CLIENTE" in tables else []:
                item = self._map_cliente(row)
                if item.get("nome"):
                    cliente_sources.add(item["source_id"])
                    cliente_name_by_source[item["source_id"]] = item["nome"]
                dup, _ = self._cliente_duplicate(item)
                if dup:
                    cliente_by_source[item["source_id"]] = dup
            for row in self._os_rows():
                item = self._map_os(row, cliente_by_source)
                if item["cliente_source_id"] not in cliente_sources:
                    invalid["ordens_servico"].append({"source_id": item["source_id"], "reason": "cliente externo ausente ou sem nome"})
                elif item.get("cliente"):
                    dup, reason = self._os_duplicate(item)
                    if dup:
                        duplicates["ordens_servico"].append({"source_id": item["source_id"], "reason": reason, "zokyo_id": dup.id})
                if len(examples["ordens_servico"]) < 10:
                    copy = dict(item)
                    copy["cliente"] = item["cliente"].id if item.get("cliente") else None
                    copy["cliente_previsto"] = cliente_name_by_source.get(item["cliente_source_id"])
                    examples["ordens_servico"].append(copy)

        if "CONTAPAGAR" in tables:
            selected.append("CONTAPAGAR")
            for row in self._contapagar_rows():
                item = self._map_financeiro(row, "despesa")
                if item["valor"] <= 0:
                    invalid["financeiro"].append({"source_id": item["source_id"], "reason": "valor vazio ou zerado"})
                    continue
                if self._transacao_duplicate(item):
                    duplicates["financeiro"].append({"source_id": item["source_id"], "reason": "lançamento semelhante já existe"})
                if len(examples["financeiro"]) < 10:
                    examples["financeiro"].append(item)

        if "CONTARECEBER" in tables:
            selected.append("CONTARECEBER")
            for row in self._contareceber_rows():
                item = self._map_financeiro(row, "receita")
                if item["valor"] <= 0:
                    invalid["financeiro"].append({"source_id": item["source_id"], "reason": "valor vazio ou zerado"})
                    continue
                if self._transacao_duplicate(item):
                    duplicates["financeiro"].append({"source_id": item["source_id"], "reason": "lançamento semelhante já existe"})
                if len(examples["financeiro"]) < 10:
                    examples["financeiro"].append(item)

        return {
            "success": True,
            "dry_run": True,
            "connection": self.test_connection(),
            "schema": schema,
            "selected_tables": sorted(set(selected)),
            "counts": {
                "clientes": self._scalar("SELECT COUNT(*) FROM CLIENTE") if "CLIENTE" in tables else 0,
                "produtos": self._scalar("SELECT COUNT(*) FROM PRODUTO") if "PRODUTO" in tables else 0,
                "ordens_servico": self._scalar("SELECT COUNT(*) FROM OS_ORDEMSERVICO") if "OS_ORDEMSERVICO" in tables else 0,
                "financeiro": (
                    (self._scalar("SELECT COUNT(*) FROM CONTAPAGAR") if "CONTAPAGAR" in tables else 0)
                    + (self._scalar("SELECT COUNT(*) FROM CONTARECEBER") if "CONTARECEBER" in tables else 0)
                ),
            },
            "mapped_fields": self.mapping_report(),
            "ignored_fields": self.ignored_fields_report(),
            "invalid_records": invalid,
            "probable_duplicates": duplicates,
            "examples": examples,
            "manual_confirmation": self.manual_confirmation_report(),
        }

    def commit(self, admin_user: str | None = None, admin_user_id: int | None = None) -> dict[str, Any]:
        if not admin_user_id:
            raise ExternalImportError("Usuário admin da sessão não identificado.")
        organization_id = getattr(g, "organization_id", None) if has_request_context() else None
        if not organization_id:
            admin_user_obj = db.session.get(
                Usuario, admin_user_id, execution_options={"include_all_tenants": True}
            )
            organization_id = admin_user_obj.organization_id if admin_user_obj else None
        if not organization_id:
            raise ExternalImportError("Organização do usuário admin não identificada.")
        preview = self.preview()
        tables = set(preview.get("schema", {}).get("tables", {}))
        created = {"clientes": 0, "produtos": 0, "ordens_servico": 0, "financeiro": 0, "itens_os": 0}
        skipped = {"clientes": 0, "produtos": 0, "ordens_servico": 0, "financeiro": 0, "itens_os": 0}
        errors = []
        cliente_by_source = {}
        produto_by_source = {}
        items_by_os = self._items_by_os() if "OS_PRODSERV" in tables else {}

        try:
            for row in self._cliente_rows() if "CLIENTE" in tables else []:
                item = self._map_cliente(row)
                if not item["nome"]:
                    skipped["clientes"] += 1
                    continue
                dup, _ = self._cliente_duplicate(item)
                if dup:
                    cliente_by_source[item["source_id"]] = dup
                    skipped["clientes"] += 1
                    continue
                cliente = Cliente(
                    nome=item["nome"],
                    cpf=item["cpf"],
                    cnpj=item["cnpj"],
                    telefone=item["telefone"],
                    email=item["email"],
                    cep=item["cep"],
                    endereco=item["endereco"],
                    numero_casa=item["numero_casa"],
                    cidade=item["cidade"],
                    uf=item["uf"],
                )
                db.session.add(cliente)
                db.session.flush()
                cliente_by_source[item["source_id"]] = cliente
                created["clientes"] += 1

            for row in self._produto_rows() if "PRODUTO" in tables else []:
                item = self._map_produto(row)
                if not item["nome"]:
                    skipped["produtos"] += 1
                    continue
                dup, _ = self._produto_duplicate(item)
                if dup:
                    produto_by_source[item["source_id"]] = dup
                    skipped["produtos"] += 1
                    continue
                peca = Peca(
                    nome=item["nome"],
                    codigo=item["codigo"],
                    categoria=item["categoria"],
                    quantidade=item["quantidade"],
                    estoque_minimo=0,
                    custo=item["custo"],
                    margem=item["margem"],
                )
                db.session.add(peca)
                db.session.flush()
                produto_by_source[item["source_id"]] = peca
                created["produtos"] += 1

            for row in self._os_rows() if "OS_ORDEMSERVICO" in tables else []:
                item = self._map_os(row, cliente_by_source)
                if not item.get("cliente"):
                    skipped["ordens_servico"] += 1
                    continue
                dup, reason = self._os_duplicate(item)
                if dup:
                    skipped["ordens_servico"] += 1
                    continue
                os_obj = OrdemServico(
                    numero=item["numero"] or proximo_numero_os(organization_id),
                    cliente_id=item["cliente"].id,
                    usuario_id=admin_user_id,
                    tipo_aparelho=item["tipo_aparelho"],
                    marca=item["marca"],
                    modelo=item["modelo"],
                    numero_serie=item["numero_serie"],
                    defeito_alegado=item["defeito_alegado"],
                    solucao=item["solucao"],
                    observacoes=item["observacoes"],
                    valor_servico=item["valor_servico"],
                    status=item["status"],
                    tecnico_nome=item["tecnico_nome"],
                    garantia_dias=item["garantia_dias"],
                    data_entrada=item["data_entrada"],
                    data_saida=item["data_saida"],
                )
                db.session.add(os_obj)
                db.session.flush()
                valor_pecas = Decimal("0")
                valor_servicos = Decimal("0")
                for item_row in items_by_os.get(item["source_id"], []):
                    qty = Decimal(str(item_row.get("QUANTIDADE") or 0))
                    unit = Decimal(str(item_row.get("VALORUNITARIO") or 0))
                    total = Decimal(str(item_row.get("VALORTOTAL") or (qty * unit) or 0))
                    source_prod = str(item_row.get("CODPROD") or "").strip()
                    item_type = str(item_row.get("TIPO") or "").upper()
                    peca = produto_by_source.get(source_prod)
                    if item_type == "P" and peca:
                        if (
                            os_obj.organization_id != organization_id
                            or peca.organization_id != organization_id
                        ):
                            raise ExternalImportError(
                                "Item de OS pertence a outra organização."
                            )
                        db.session.execute(
                            text(
                                "INSERT INTO os_pecas "
                                "(os_id, peca_id, quantidade, valor_unitario, "
                                "custo_unitario, link_compra) "
                                "SELECT :o, :p, :q, :v, NULL, NULL "
                                "FROM ordens_servico o, pecas p "
                                "WHERE o.id=:o AND p.id=:p "
                                "AND o.organization_id=:org "
                                "AND p.organization_id=:org"
                            ),
                            {
                                "o": os_obj.id, "p": peca.id,
                                "q": int(qty or 1), "v": unit,
                                "org": organization_id,
                            },
                        )
                        valor_pecas += total
                        created["itens_os"] += 1
                    else:
                        valor_servicos += total
                        if item_row.get("NOMEPROD"):
                            extra = sanitize_text(item_row.get("NOMEPROD"), max_length=200)
                            os_obj.observacoes = "\n".join(part for part in [os_obj.observacoes, f"Serviço importado: {extra}"] if part)
                            created["itens_os"] += 1
                if valor_pecas:
                    os_obj.valor_pecas = valor_pecas
                if valor_servicos:
                    os_obj.valor_servico = valor_servicos
                db.session.add(OSHistorico(os_id=os_obj.id, usuario_id=admin_user_id, status_anterior=None, status_novo=os_obj.status))
                created["ordens_servico"] += 1

            for row in self._contapagar_rows() if "CONTAPAGAR" in tables else []:
                item = self._map_financeiro(row, "despesa")
                if item["valor"] <= 0 or self._transacao_duplicate(item):
                    skipped["financeiro"] += 1
                    continue
                db.session.add(Transacao(**{k: v for k, v in item.items() if k != "source_id"}))
                created["financeiro"] += 1

            for row in self._contareceber_rows() if "CONTARECEBER" in tables else []:
                item = self._map_financeiro(row, "receita")
                if item["valor"] <= 0 or self._transacao_duplicate(item):
                    skipped["financeiro"] += 1
                    continue
                db.session.add(Transacao(**{k: v for k, v in item.items() if k != "source_id"}))
                created["financeiro"] += 1

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            errors.append(str(exc))
            raise
        finally:
            self._write_log(admin_user, created, skipped, errors, preview)

        return {
            "success": True,
            "commit": True,
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "preview_summary": {
                "selected_tables": preview["selected_tables"],
                "counts": preview["counts"],
            },
        }

    def mapping_report(self):
        return {
            "clientes": {
                "CLIENTE.NOMECLI": "Cliente.nome",
                "CLIENTE.CPF": "Cliente.cpf",
                "CLIENTE.CNPJ": "Cliente.cnpj",
                "CLIENTE.TELEFONE": "Cliente.telefone",
                "CLIENTE.EMAIL": "Cliente.email",
                "CLIENTE.CEP": "Cliente.cep",
                "CLIENTE.ENDERECO": "Cliente.endereco + Cliente.numero_casa quando separavel",
                "CLIENTE.CIDADE": "Cliente.cidade",
                "CLIENTE.ESTADO": "Cliente.uf",
            },
            "produtos": {
                "PRODUTO.CODIGO": "Peca.codigo",
                "PRODUTO.NOMEPROD": "Peca.nome",
                "SECAO.NOMESECAO": "Peca.categoria",
                "PRODUTOESTOQUE.ESTATU": "Peca.quantidade",
                "PRODUTO.PRECUSTO": "Peca.custo",
                "PRODUTOPRECO.PRECO": "Peca.margem calculada",
            },
            "ordens_servico": {
                "OS_ORDEMSERVICO.NUMOS": "OrdemServico.numero",
                "OS_ORDEMSERVICO.CODCLI": "OrdemServico.cliente_id via CLIENTE.CODCLI",
                "OS_ORDEMSERVICO.EQUIPAMENTO": "OrdemServico.tipo_aparelho",
                "OS_ORDEMSERVICO.MARCAMODELO": "OrdemServico.marca/modelo quando separavel",
                "OS_ORDEMSERVICO.IDENTIFICADOR": "OrdemServico.numero_serie",
                "OS_ORDEMSERVICO.OCORRENCIA": "OrdemServico.defeito_alegado",
                "OS_ORDEMSERVICO.SOLUCAO": "OrdemServico.solucao",
                "OS_ORDEMSERVICO.OBS": "OrdemServico.observacoes",
                "OS_STATUS.STATUS": "OrdemServico.status normalizado",
                "OS_ORDEMSERVICO.DATA": "OrdemServico.data_entrada",
                "OS_ORDEMSERVICO.DATSAI": "OrdemServico.data_saida",
                "OS_PRODSERV.VALORTOTAL": "OrdemServico.valor_servico somado",
                "OS_PRODSERV.TIPO='P'": "Peças vinculadas na OS quando o produto existir",
                "OS_PRODSERV.TIPO!='P'": "Serviços somados em mão de obra e anotados em observações",
                "OS_TECNICO.TECNICO": "OrdemServico.tecnico_nome",
            },
            "financeiro": {
                "CONTAPAGAR": "Transacao despesa",
                "CONTARECEBER": "Transacao receita",
                "VALOR/VALORPG": "Transacao.valor",
                "DATVENC": "Transacao.data_vencimento",
                "DATPAG": "Transacao.data_pagamento",
                "FLAGPAGO": "Transacao.status",
            },
        }

    def ignored_fields_report(self):
        return {
            "clientes": ["CLIENTE.OBS", "CLIENTE.FOTO", "campos fiscais/comerciais sem equivalente direto"],
            "produtos": ["PRODUTO.UNIDADE", "PRODUTO.OBS", "campos fiscais sem equivalente direto"],
            "ordens_servico": ["acessórios sem campo dedicado ficam em observações", "campos de agenda/KM/cupom/movenda"],
        }

    def manual_confirmation_report(self):
        return [
            "Confirmar se todos os status devem seguir a normalização automática.",
            "Confirmar separação marca/modelo quando o campo de origem não contiver '/' ou '-'.",
            "Confirmar se produtos marcados como serviço devem entrar no estoque ou ficar apenas nas observações da OS.",
            "Commit exige usuário admin autenticado para vincular histórico de OS importada.",
        ]

    def _write_log(self, admin_user, created, skipped, errors, preview):
        if not has_app_context():
            return
        folder = Path(current_app.instance_path) / "import_logs"
        folder.mkdir(parents=True, exist_ok=True)
        organization_id = getattr(g, "organization_id", None) if has_request_context() else None
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organization_id": organization_id,
            "admin_user": admin_user,
            "source_type": "firebird",
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "problematic_records": preview.get("invalid_records", {}),
            "probable_duplicates": preview.get("probable_duplicates", {}),
        }
        org_suffix = f"org{organization_id}_" if organization_id else ""
        path = folder / (
            f"external_import_{org_suffix}"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_safe), encoding="utf-8")


class GenericExternalImporter(ExternalFirebirdImporter):
    """Adaptador para exportações comuns de sistemas de assistência técnica.

    A maioria dos sistemas não expõe um schema público estável. Por isso o
    importador trabalha com tabelas/planilhas e aliases de colunas, mantendo a
    confirmação manual antes de gravar dados no tenant.
    """

    _CLIENT_ALIASES = {
        "CODCLI": ("id", "codigo", "codcli", "customer_id", "client_id"),
        "NOMECLI": ("nome", "name", "cliente", "customer", "nomecli", "razao_social"),
        "CPF": ("cpf", "documento", "cpf_cnpj"),
        "CNPJ": ("cnpj",),
        "TELEFONE": ("telefone", "phone", "celular", "fone"),
        "EMAIL": ("email", "e_mail", "mail"),
        "CEP": ("cep", "postal_code", "zipcode"),
        "ENDERECO": ("endereco", "address", "logradouro", "rua"),
        "CIDADE": ("cidade", "city"),
        "ESTADO": ("estado", "uf", "state"),
    }
    _PRODUCT_ALIASES = {
        "CODPROD": ("id", "codigo_id", "codprod", "product_id", "part_id"),
        "CODIGO": ("codigo", "sku", "ref", "referencia", "part_number"),
        "NOMEPROD": ("nome", "name", "produto", "product", "descricao", "description"),
        "CATEGORIA": ("categoria", "category", "grupo", "section"),
        "QUANTIDADE": ("quantidade", "quantity", "estoque", "stock", "saldo"),
        "PRECUSTO": ("custo", "cost", "preco_custo", "purchase_price"),
        "PRECO": ("preco", "price", "preco_venda", "sale_price"),
        "UNIDADE": ("unidade", "unit"),
        "OBS": ("observacao", "observacoes", "obs", "notes"),
    }
    _OS_ALIASES = {
        "CODOS": ("id", "codigo", "codos", "os_id", "order_id", "ticket_id"),
        "NUMOS": ("numero", "numero_os", "numos", "number", "order_number"),
        "CODCLI": ("cliente_id", "client_id", "customer_id", "codcli"),
        "EQUIPAMENTO": ("equipamento", "device", "tipo_aparelho", "asset"),
        "IDENTIFICADOR": ("numero_serie", "serial", "serial_number", "imei"),
        "MARCAMODELO": ("marca_modelo", "brand_model", "marcamodelo", "modelo"),
        "OCORRENCIA": ("defeito", "problema", "ocorrencia", "issue", "complaint"),
        "SOLUCAO": ("solucao", "solution", "resolucao", "resolution"),
        "OBS": ("observacao", "observacoes", "obs", "notes"),
        "STATUS_NOME": ("status", "situacao", "state"),
        "DATA": ("data", "data_entrada", "opened_at", "created_at", "entry_date"),
        "DATSAI": ("data_saida", "closed_at", "finished_at", "exit_date"),
        "GARANTIA": ("garantia", "warranty_days"),
        "TECNICO_NOME": ("tecnico", "technician", "technician_name", "assigned_to"),
        "VALOR": ("valor", "total", "amount", "price"),
    }
    _FIN_ALIASES = {
        "CODCP": ("id", "codigo", "codcp", "codcr", "transaction_id"),
        "ORIGEM": ("descricao", "description", "origem", "historico", "history"),
        "CREDOR": ("credor", "fornecedor", "supplier", "payee"),
        "DEVEDOR": ("devedor", "cliente", "customer", "payer"),
        "VALOR": ("valor", "amount", "total", "price"),
        "VALORPG": ("valor_pago", "paid_amount"),
        "DATVENC": ("vencimento", "data_vencimento", "due_date"),
        "DATPAG": ("pagamento", "data_pagamento", "paid_at"),
        "FLAGPAGO": ("pago", "status", "paid"),
        "LOCAL": ("forma_pagamento", "payment_method", "local"),
        "TIPO": ("tipo", "type", "kind"),
    }

    def __init__(self, credentials: FirebirdCredentials):
        super().__init__(credentials)
        self._tables_cache: dict[str, list[dict[str, Any]]] | None = None

    @property
    def source_type(self):
        return (self.credentials.source_type or "csv").lower()

    @staticmethod
    def _key(value):
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")

    def _normal_row(self, row):
        return {self._key(k): v for k, v in row.items() if k is not None}

    def _read_sqlite(self, path):
        if not Path(path).exists():
            raise ExternalImportError("Arquivo SQLite não encontrado no servidor.")
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()]
            return {name: [dict(row) for row in con.execute(f'"{name.replace(chr(34), chr(34) * 2)}"').fetchall()] for name in names}
        except sqlite3.Error as exc:
            raise ExternalImportError(f"Não foi possível ler o SQLite: {exc}") from exc
        finally:
            con.close()

    def _read_mysql(self):
        try:
            import pymysql
        except ImportError as exc:
            raise ExternalImportError("O driver PyMySQL não está instalado para MySQL/MariaDB.") from exc
        try:
            con = pymysql.connect(
                host=self.credentials.host or "127.0.0.1",
                port=int(self.credentials.port or 3306),
                user=self.credentials.user,
                password=self.credentials.password,
                database=self.credentials.database,
                charset=self.credentials.charset or "utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
            )
            with con.cursor() as cur:
                cur.execute("SHOW TABLES")
                names = [next(iter(row.values())) for row in cur.fetchall()]
                tables = {}
                for name in names:
                    cur.execute(f"SELECT * FROM `{str(name).replace('`', '``')}` LIMIT 100000")
                    tables[str(name)] = list(cur.fetchall())
            return tables
        except Exception as exc:
            raise ExternalImportError(f"Não foi possível ler MySQL/MariaDB: {exc}") from exc
        finally:
            try:
                con.close()
            except UnboundLocalError:
                pass

    def _read_file(self, path):
        if not Path(path).exists():
            raise ExternalImportError("Arquivo de importação não encontrado no servidor.")
        suffix = Path(path).suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            try:
                from openpyxl import load_workbook
                workbook = load_workbook(path, read_only=True, data_only=True)
            except ImportError as exc:
                raise ExternalImportError("O suporte a XLSX exige o pacote openpyxl.") from exc
            except Exception as exc:
                raise ExternalImportError(f"Não foi possível ler a planilha: {exc}") from exc
            tables = {}
            for sheet in workbook.worksheets:
                if self.credentials.sheet and sheet.title != self.credentials.sheet:
                    continue
                values = sheet.iter_rows(values_only=True)
                headers = next(values, ())
                tables[sheet.title] = [dict(zip(headers, row)) for row in values if any(v is not None for v in row)]
            return tables
        if suffix == ".zip":
            tables = {}
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        if Path(name).suffix.lower() != ".csv" or name.endswith("/"):
                            continue
                        with archive.open(name) as stream:
                            text_stream = stream.read().decode(self.credentials.charset or "utf-8-sig", errors="replace").splitlines()
                        reader = csv.DictReader(text_stream, delimiter=self.credentials.delimiter or ",")
                        tables[Path(name).stem] = list(reader)
            except (OSError, zipfile.BadZipFile) as exc:
                raise ExternalImportError(f"Não foi possível ler o ZIP de importação: {exc}") from exc
            return tables
        try:
            with open(path, "r", encoding=self.credentials.charset or "utf-8-sig", newline="") as stream:
                sample = stream.read(4096)
                stream.seek(0)
                delimiter = self.credentials.delimiter or csv.Sniffer().sniff(sample).delimiter
                return {Path(path).stem: list(csv.DictReader(stream, delimiter=delimiter))}
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ExternalImportError(f"Não foi possível ler o CSV: {exc}") from exc

    def _load_tables(self):
        if self._tables_cache is not None:
            return self._tables_cache
        kind = self.source_type
        if kind == "sqlite":
            tables = self._read_sqlite(self.credentials.database_path)
        elif kind in {"mysql", "mariadb"}:
            tables = self._read_mysql()
        elif kind in {"csv", "xlsx", "xls", "zip"}:
            tables = self._read_file(self.credentials.database_path)
        else:
            raise ExternalImportError(f"Tipo de origem não suportado: {kind}.")
        self._tables_cache = {
            str(name): [self._normal_row(row) for row in rows]
            for name, rows in tables.items()
        }
        if not self._tables_cache:
            raise ExternalImportError("A origem não possui tabelas ou linhas para importar.")
        return self._tables_cache

    def _table_role(self, name):
        key = self._key(name)
        if key in {"cliente", "clientes", "client", "clients", "customer", "customers"} or "cliente" in key or "customer" in key:
            return "clientes"
        if key in {"produto", "produtos", "product", "products", "peca", "pecas", "parts", "inventory", "estoque"} or "produto" in key:
            return "produtos"
        if key in {"os", "ordem_servico", "ordens_servico", "order", "orders", "service_order", "service_orders", "tickets", "chamados"} or "ordem" in key or "ticket" in key:
            return "ordens_servico"
        if key in {"financeiro", "transacoes", "transacao", "lancamentos", "lancamento", "contas_pagar", "contas_receber", "payments"} or "finance" in key:
            return "financeiro"
        return None

    def _tables_for(self, role):
        tables = self._load_tables()
        found = [(name, rows) for name, rows in tables.items() if self._table_role(name) == role]
        if found:
            return found
        profile = self.credentials.profile.lower()
        if len(tables) == 1:
            if profile == role:
                return list(tables.items())
            if profile == "auto":
                name, rows = next(iter(tables.items()))
                keys = set(rows[0]) if rows else set()
                alias_sets = {
                    "clientes": self._CLIENT_ALIASES,
                    "produtos": self._PRODUCT_ALIASES,
                    "ordens_servico": self._OS_ALIASES,
                    "financeiro": self._FIN_ALIASES,
                }
                scores = {candidate: len(keys & set(sum((list(v) for v in aliases.values()), [])))
                          for candidate, aliases in alias_sets.items()}
                best = max(scores, key=scores.get) if scores else None
                if best == role and scores.get(best, 0) >= 1:
                    return [(name, rows)]
        return []

    @staticmethod
    def _pick(row, aliases):
        for alias in aliases:
            value = row.get(alias)
            if value not in (None, ""):
                return value
        return None

    def _canonical_rows(self, role, aliases):
        result = []
        for _, rows in self._tables_for(role):
            for row in rows:
                result.append({key: self._pick(row, values) for key, values in aliases.items()})
        return result

    def _cliente_rows(self):
        return self._canonical_rows("clientes", self._CLIENT_ALIASES)

    def _produto_rows(self):
        return self._canonical_rows("produtos", self._PRODUCT_ALIASES)

    def _os_rows(self):
        return self._canonical_rows("ordens_servico", self._OS_ALIASES)

    def _contapagar_rows(self):
        rows = self._canonical_rows("financeiro", self._FIN_ALIASES)
        result = [row for row in rows if str(row.get("TIPO") or "").lower() in {"despesa", "expense", "pagar", "payable"}]
        for row in result:
            row["FLAGPAGO"] = "Y" if str(row.get("FLAGPAGO") or "").lower() in {"y", "yes", "sim", "pago", "paid", "1", "true"} else "N"
        return result

    def _contareceber_rows(self):
        rows = self._canonical_rows("financeiro", self._FIN_ALIASES)
        expenses = self._contapagar_rows()
        result = [row for row in rows if row not in expenses]
        for row in result:
            row["FLAGPAGO"] = "Y" if str(row.get("FLAGPAGO") or "").lower() in {"y", "yes", "sim", "pago", "paid", "1", "true"} else "N"
        return result

    def _scalar(self, sql, params=()):
        table = re.search(r"FROM\s+([A-Z0-9_]+)", sql.upper())
        if not table:
            return 0
        mapping = {"CLIENTE": self._cliente_rows, "PRODUTO": self._produto_rows, "OS_ORDEMSERVICO": self._os_rows,
                   "CONTAPAGAR": self._contapagar_rows, "CONTARECEBER": self._contareceber_rows}
        return len(mapping.get(table.group(1), lambda: [])())

    def _rows(self, sql, params=()):
        return []

    def _items_by_os(self):
        return {}

    def _connect(self):
        self._load_tables()
        return None

    def test_connection(self):
        tables = self._load_tables()
        return {"success": True, "driver": self.source_type, "table_count": len(tables)}

    def inspect_schema(self):
        tables = self._load_tables()
        schema = {"table_count": len(tables), "tables": {}}
        for name, rows in tables.items():
            first = rows[0] if rows else {}
            schema["tables"][name] = {
                "columns": [{"name": key, "type": type(value).__name__.upper(), "nullable": True} for key, value in first.items()],
                "primary_key": [], "foreign_keys": [],
            }
        for canonical, rows in (("CLIENTE", self._cliente_rows()), ("PRODUTO", self._produto_rows()),
                                ("OS_ORDEMSERVICO", self._os_rows()), ("CONTAPAGAR", self._contapagar_rows()),
                                ("CONTARECEBER", self._contareceber_rows())):
            if rows:
                schema["tables"][canonical] = {"columns": [{"name": key, "type": "MAPPED", "nullable": True} for key in rows[0]], "primary_key": [], "foreign_keys": []}
        schema["detected_entities"] = self.detect_entities(schema)
        return schema

    def detect_entities(self, schema):
        tables = set(schema.get("tables", {}))
        return {
            "clientes": ["CLIENTE"] if "CLIENTE" in tables else [],
            "clientes_auxiliares": [],
            "produtos": ["PRODUTO"] if "PRODUTO" in tables else [],
            "ordens_servico": ["OS_ORDEMSERVICO"] if "OS_ORDEMSERVICO" in tables else [],
            "financeiro": [t for t in ("CONTARECEBER", "CONTAPAGAR") if t in tables],
            "compatibilidade": {
                "sqlite": self.source_type == "sqlite",
                "mysql_mariadb": self.source_type in {"mysql", "mariadb"},
                "csv_planilha": self.source_type in {"csv", "xlsx", "xls", "zip"},
                "perfis_alias": True,
            },
        }

    def mapping_report(self):
        return {
            "clientes": {", ".join(values): f"Cliente.{key.lower()}" for key, values in self._CLIENT_ALIASES.items()},
            "produtos": {", ".join(values): f"Peca.{key.lower()}" for key, values in self._PRODUCT_ALIASES.items()},
            "ordens_servico": {", ".join(values): f"OrdemServico.{key.lower()}" for key, values in self._OS_ALIASES.items()},
            "financeiro": {", ".join(values): f"Transacao.{key.lower()}" for key, values in self._FIN_ALIASES.items()},
        }

    def ignored_fields_report(self):
        return {"geral": ["Colunas sem alias reconhecido são ignoradas.", "Itens de OS/peças exigem exportação separada e ficam para revisão manual."],
                "perfis": ["Use nomes de tabela clientes, produtos, os e lancamentos para detecção automática."]}

    def _write_log(self, admin_user, created, skipped, errors, preview):
        if not has_app_context():
            return
        folder = Path(current_app.instance_path) / "import_logs"
        folder.mkdir(parents=True, exist_ok=True)
        organization_id = getattr(g, "organization_id", None) if has_request_context() else None
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "organization_id": organization_id,
                   "admin_user": admin_user, "source_type": self.source_type, "created": created,
                   "skipped": skipped, "errors": errors, "problematic_records": preview.get("invalid_records", {}),
                   "probable_duplicates": preview.get("probable_duplicates", {})}
        path = folder / f"external_import_org{organization_id or 'unknown'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_safe), encoding="utf-8")
