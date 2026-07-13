"""Servico de importacao CPlus/Firebird para o Zokyo."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import current_app, has_app_context

from app.extensions import db
from app.models import Cliente, OrdemServico, OSHistorico, Peca
from app.utils.sanitizers import sanitize_cep, sanitize_phone, sanitize_text
from app.utils.validators import validar_cnpj, validar_cpf


class CPlusImportError(RuntimeError):
    """Erro amigavel de importacao CPlus."""


@dataclass
class FirebirdCredentials:
    database_path: str
    user: str = "SYSDBA"
    password: str = ""
    charset: str = "WIN1252"


def _digits(value: Any, limit: int | None = None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:limit] if limit else digits


def _json_safe(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


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


class CPlusFirebirdImporter:
    def __init__(self, credentials: FirebirdCredentials):
        self.credentials = credentials
        self._driver = None

    def _connect(self):
        db_path = Path(self.credentials.database_path)
        if not db_path.exists():
            raise CPlusImportError("Arquivo .fdb nao encontrado no servidor.")

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
            errors.append(f"fdb nao instalado: {exc}")
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
            errors.append(f"firebird-driver nao instalado: {exc}")
        except Exception as exc:
            errors.append(str(exc))

        detail = " | ".join(errors) or "Cliente Firebird indisponivel."
        raise CPlusImportError(
            "Nao foi possivel abrir o Firebird. Instale Firebird Client/Server "
            "compativel com o .fdb ou defina FIREBIRD_CLIENT_LIBRARY. Detalhe: "
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
        }

    def _split_address(self, endereco):
        text = sanitize_text(endereco, max_length=300)
        if not text:
            return None, None, None
        match = re.match(r"^(.*?)[,\s]+(\d+[A-Za-z0-9\-\/]*)$", text)
        if match and len(match.group(1).strip()) >= 3:
            return match.group(1).strip(), match.group(2).strip(), None
        return text, None, "Numero da casa nao separado com seguranca."

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
            "cep": sanitize_cep(row.get("CEP")) or None,
            "endereco": endereco,
            "numero_casa": numero,
            "cidade": sanitize_text(row.get("CIDADE"), max_length=100) or None,
            "uf": sanitize_text(row.get("ESTADO"), max_length=2).upper() or None,
            "warning": warning,
        }

    def _cliente_duplicate(self, item):
        if item.get("cpf"):
            found = Cliente.query.filter_by(cpf=item["cpf"]).first()
            if found:
                return found, "CPF ja existe"
        if item.get("cnpj"):
            found = Cliente.query.filter_by(cnpj=item["cnpj"]).first()
            if found:
                return found, "CNPJ ja existe"
        if item.get("nome") and item.get("telefone"):
            found = Cliente.query.filter_by(nome=item["nome"], telefone=item["telefone"]).first()
            if found:
                return found, "nome + telefone ja existem"
        return None, None

    def _cliente_rows(self):
        return self._rows("""
            SELECT CODCLI, NOMECLI, CPF, CNPJ, TELEFONE, CEP, ENDERECO, CIDADE, ESTADO
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
                return found, "codigo ja existe"
        found = Peca.query.filter_by(nome=item["nome"]).first() if item.get("nome") else None
        if found:
            return found, "nome ja existe"
        return None, None

    def _os_rows(self):
        return self._rows("""
            SELECT os.CODOS, os.CODCLI, os.EQUIPAMENTO, os.IDENTIFICADOR, os.MARCAMODELO,
                   os.TIPO, os.OCORRENCIA, os.OBS, os.SOLUCAO, os.DATA, os.DATSAI,
                   os.GARANTIA, os.CODSTATUS, os.CODTEC,
                   st.STATUS AS STATUS_NOME,
                   tec.TECNICO AS TECNICO_NOME,
                   COALESCE(SUM(ps.VALORTOTAL), 0) AS VALOR
            FROM OS_ORDEMSERVICO os
            LEFT JOIN OS_STATUS st ON st.CODSTATUS = os.CODSTATUS
            LEFT JOIN OS_TECNICO tec ON tec.CODTEC = os.CODTEC
            LEFT JOIN OS_PRODSERV ps ON ps.CODOS = os.CODOS
            GROUP BY os.CODOS, os.CODCLI, os.EQUIPAMENTO, os.IDENTIFICADOR, os.MARCAMODELO,
                     os.TIPO, os.OCORRENCIA, os.OBS, os.SOLUCAO, os.DATA, os.DATSAI,
                     os.GARANTIA, os.CODSTATUS, os.CODTEC, st.STATUS, tec.TECNICO
            ORDER BY os.CODOS
        """)

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
            "data_entrada": row.get("DATA"),
            "data_saida": row.get("DATSAI"),
            "valor_servico": float(row.get("VALOR") or 0),
            "garantia_dias": int(row.get("GARANTIA") or 90),
            "tecnico_nome": sanitize_text(row.get("TECNICO_NOME"), max_length=120) or None,
        }

    def _os_duplicate(self, item):
        if not item.get("cliente"):
            return None, "cliente ausente"
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
            return found, "OS semelhante ja existe"
        return None, None

    def preview(self) -> dict[str, Any]:
        schema = self.inspect_schema()
        tables = set(schema["tables"])
        selected = []
        invalid = {"clientes": [], "produtos": [], "ordens_servico": []}
        duplicates = {"clientes": [], "produtos": [], "ordens_servico": []}
        examples = {"clientes": [], "produtos": [], "ordens_servico": []}

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
            cliente_sources = set()
            for row in self._cliente_rows() if "CLIENTE" in tables else []:
                item = self._map_cliente(row)
                if item.get("nome"):
                    cliente_sources.add(item["source_id"])
                dup, _ = self._cliente_duplicate(item)
                if dup:
                    cliente_by_source[item["source_id"]] = dup
            for row in self._os_rows():
                item = self._map_os(row, cliente_by_source)
                if item["cliente_source_id"] not in cliente_sources:
                    invalid["ordens_servico"].append({"source_id": item["source_id"], "reason": "cliente CPlus ausente ou sem nome"})
                elif item.get("cliente"):
                    dup, reason = self._os_duplicate(item)
                    if dup:
                        duplicates["ordens_servico"].append({"source_id": item["source_id"], "reason": reason, "zokyo_id": dup.id})
                if len(examples["ordens_servico"]) < 10:
                    copy = dict(item)
                    copy["cliente"] = item["cliente"].id if item.get("cliente") else None
                    examples["ordens_servico"].append(copy)

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
            raise CPlusImportError("Usuario admin da sessao nao identificado.")
        preview = self.preview()
        created = {"clientes": 0, "produtos": 0, "ordens_servico": 0}
        skipped = {"clientes": 0, "produtos": 0, "ordens_servico": 0}
        errors = []
        cliente_by_source = {}

        try:
            for row in self._cliente_rows():
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

            for row in self._produto_rows():
                item = self._map_produto(row)
                if not item["nome"]:
                    skipped["produtos"] += 1
                    continue
                dup, _ = self._produto_duplicate(item)
                if dup:
                    skipped["produtos"] += 1
                    continue
                db.session.add(Peca(
                    nome=item["nome"],
                    codigo=item["codigo"],
                    categoria=item["categoria"],
                    quantidade=item["quantidade"],
                    estoque_minimo=0,
                    custo=item["custo"],
                    margem=item["margem"],
                ))
                created["produtos"] += 1

            for row in self._os_rows():
                item = self._map_os(row, cliente_by_source)
                if not item.get("cliente"):
                    skipped["ordens_servico"] += 1
                    continue
                dup, reason = self._os_duplicate(item)
                if dup:
                    skipped["ordens_servico"] += 1
                    continue
                os_obj = OrdemServico(
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
                db.session.add(OSHistorico(os_id=os_obj.id, usuario_id=admin_user_id, status_anterior=None, status_novo=os_obj.status))
                created["ordens_servico"] += 1

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
                "OS_TECNICO.TECNICO": "OrdemServico.tecnico_nome",
            },
        }

    def ignored_fields_report(self):
        return {
            "clientes": ["CLIENTE.EMAIL (cliente nao usa mais e-mail)", "CLIENTE.OBS", "CLIENTE.FOTO", "campos fiscais/comerciais"],
            "produtos": ["PRODUTO.UNIDADE (modelo Peca nao possui unidade)", "PRODUTO.OBS (modelo Peca nao possui observacoes)", "campos fiscais"],
            "ordens_servico": ["acessorios sem campo dedicado ficam em observacoes", "campos de agenda/KM/cupom/movenda"],
        }

    def manual_confirmation_report(self):
        return [
            "Confirmar se todos os status OS_STATUS devem seguir a normalizacao automatica.",
            "Confirmar separacao marca/modelo quando MARCAMODELO nao contiver '/' ou '-'.",
            "Confirmar se produtos de servico devem entrar no estoque ou ficar fora.",
            "Commit exige usuario admin autenticado para vincular historico de OS importada.",
        ]

    def _write_log(self, admin_user, created, skipped, errors, preview):
        if not has_app_context():
            return
        folder = Path(current_app.instance_path) / "import_logs"
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "admin_user": admin_user,
            "database_path": self.credentials.database_path,
            "created": created,
            "skipped": skipped,
            "errors": errors,
            "problematic_records": preview.get("invalid_records", {}),
            "probable_duplicates": preview.get("probable_duplicates", {}),
        }
        path = folder / f"cplus_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_safe), encoding="utf-8")
