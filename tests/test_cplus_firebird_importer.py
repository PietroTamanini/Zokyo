import builtins
import json
import sys
import types
from datetime import datetime
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, Peca, Usuario
from app.services.cplus_firebird_importer import (
    CPlusFirebirdImporter,
    CPlusImportError,
    FirebirdCredentials,
    _digits,
    _json_safe,
    _type_name,
)


class FakeCursor:
    def __init__(self, rows=None, one=(3,)):
        self.description = [(" ID ",), ("NOME",)]
        self._rows = rows or [(1, "Ana")]
        self._one = one
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def _make_app(tmp_path):
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="cplus-contract-key",
        WTF_CSRF_ENABLED=False,
    )
    app.instance_path = str(tmp_path)
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="CPlus", slug="cplus")
        admin = Usuario(nome="Admin", email="cplus@example.com", nivel="admin", ativo=True, organization_id=1)
        admin.set_senha("Senha!123")
        duplicate_client = Cliente(nome="Duplicado", cpf="52998224725", telefone="47999999999", organization_id=1)
        duplicate_part = Peca(nome="Duplicada", codigo="DUP", quantidade=1, organization_id=1)
        db.session.add_all([organization, admin, duplicate_client, duplicate_part])
        db.session.flush()
        duplicate_order = OrdemServico(
            organization_id=1,
            cliente_id=duplicate_client.id,
            usuario_id=admin.id,
            tipo_aparelho="Celular",
            defeito_alegado="Tela quebrada",
            data_entrada=datetime(2026, 1, 10, 9, 0, 0),
        )
        db.session.add(duplicate_order)
        db.session.commit()
        return app, admin.id


def test_helpers_e_conexao_cobrem_drivers_firebird(monkeypatch, tmp_path):
    assert _digits("ab-123.456", 5) == "12345"
    assert _json_safe(datetime(2026, 1, 1)) == "2026-01-01T00:00:00"
    assert _json_safe(Decimal("10.50")) == 10.5
    assert _json_safe("texto") == "texto"
    assert _type_name(37, 0, 80, None, None) == "VARCHAR(80)"
    assert _type_name(16, 1, None, 12, -2) == "NUMERIC(12,2)"
    assert _type_name(16, 0, None, None, None) == "BIGINT"
    assert _type_name(261, 1, None, None, None) == "BLOB1"
    assert _type_name(999, 0, None, None, None) == "TYPE_999"

    missing = CPlusFirebirdImporter(FirebirdCredentials(str(tmp_path / "missing.fdb")))
    with pytest.raises(CPlusImportError, match="nao encontrado"):
        missing._connect()

    database = tmp_path / "base.fdb"
    database.write_text("fake", encoding="utf-8")
    cursor = FakeCursor(rows=[(7, "Maria")], one=(9,))
    calls = []

    fake_fdb = types.ModuleType("fdb")

    def connect_fdb(**kwargs):
        calls.append(kwargs)
        return FakeConnection(cursor)

    fake_fdb.connect = connect_fdb
    monkeypatch.setitem(sys.modules, "fdb", fake_fdb)
    monkeypatch.setenv("FIREBIRD_CLIENT_LIBRARY", "fbclient.dll")
    importer = CPlusFirebirdImporter(FirebirdCredentials(str(database), password="master"))
    assert importer._rows("select * from cliente") == [{"ID": 7, "NOME": "Maria"}]
    assert importer._scalar("select count(*)") == 9
    assert importer.test_connection() == {"success": True, "driver": "fdb", "table_count": 9}
    assert calls[0]["fb_library_name"] == "fbclient.dll"
    monkeypatch.delitem(sys.modules, "fdb")

    imported = []
    value_holder = types.SimpleNamespace(value=None)
    driver_module = types.ModuleType("firebird.driver")
    driver_module.driver_config = types.SimpleNamespace(fb_client_library=value_holder)

    def connect_driver(database_path, **kwargs):
        imported.append((database_path, kwargs))
        return FakeConnection(FakeCursor(one=(2,)))

    driver_module.connect = connect_driver
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fdb":
            raise ImportError("sem fdb")
        if name == "firebird.driver":
            return driver_module
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    fallback = CPlusFirebirdImporter(FirebirdCredentials(str(database), user="", password="", charset=""))
    assert fallback.test_connection()["driver"] == "firebird-driver"
    assert imported[0][0] == str(database)
    assert imported[0][1]["user"] == "SYSDBA"
    assert value_holder.value == "fbclient.dll"

    bad_fdb = types.ModuleType("fdb")
    bad_fdb.connect = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fdb quebrou"))
    bad_driver = types.ModuleType("firebird.driver")
    bad_driver.driver_config = types.SimpleNamespace(fb_client_library=types.SimpleNamespace(value=None))
    bad_driver.connect = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("driver quebrou"))

    def exception_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fdb":
            return bad_fdb
        if name == "firebird.driver":
            return bad_driver
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", exception_import)
    with pytest.raises(CPlusImportError, match="fdb quebrou"):
        CPlusFirebirdImporter(FirebirdCredentials(str(database)))._connect()

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"fdb", "firebird.driver"}:
            raise ImportError(f"{name} indisponivel")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", broken_import)
    failing = CPlusFirebirdImporter(FirebirdCredentials(str(database)))
    with pytest.raises(CPlusImportError, match="Nao foi possivel abrir"):
        failing._connect()


def test_schema_preview_commit_e_log_cplus(monkeypatch, tmp_path):
    app, admin_id = _make_app(tmp_path)
    importer = CPlusFirebirdImporter(FirebirdCredentials(str(tmp_path / "base.fdb")))
    schema_tables = {
        "CLIENTE": {},
        "CLIENTEENDERECO": {},
        "CONTATOSCLI": {},
        "PRODUTO": {},
        "PRODUTOESTOQUE": {},
        "PRODUTOPRECO": {},
        "SECAO": {},
        "OS_ORDEMSERVICO": {},
        "OS_STATUS": {},
        "OS_TECNICO": {},
        "OS_PRODSERV": {},
    }

    def fake_rows(sql, params=()):
        if "FROM rdb$relations" in sql:
            return [{"TABLE_NAME": name} for name in schema_tables]
        if "rdb$relation_fields" in sql:
            return [
                {
                    "FIELD_NAME": "CODIGO",
                    "FIELD_TYPE": 37,
                    "FIELD_SUB_TYPE": 0,
                    "FIELD_LENGTH": 20,
                    "FIELD_PRECISION": None,
                    "FIELD_SCALE": None,
                    "NULL_FLAG": 1,
                },
                {
                    "FIELD_NAME": "VALOR",
                    "FIELD_TYPE": 16,
                    "FIELD_SUB_TYPE": 1,
                    "FIELD_LENGTH": None,
                    "FIELD_PRECISION": 10,
                    "FIELD_SCALE": -2,
                    "NULL_FLAG": 0,
                },
            ]
        if "PRIMARY KEY" in sql:
            return [{"FIELD_NAME": "CODIGO"}]
        if "FOREIGN KEY" in sql:
            return [
                {
                    "CONSTRAINT_NAME": "FK_TESTE",
                    "FIELD_NAME": "CODCLI",
                    "REF_TABLE": "CLIENTE",
                    "REF_FIELD": "CODCLI",
                }
            ]
        return []

    monkeypatch.setattr(importer, "_rows", fake_rows)
    schema = importer.inspect_schema()
    assert schema["table_count"] == len(schema_tables)
    assert schema["tables"]["CLIENTE"]["columns"][0]["type"] == "VARCHAR(20)"
    assert schema["detected_entities"]["clientes"] == ["CLIENTE"]
    assert "PRODUTO" in schema["detected_entities"]["produtos"]
    assert "OS_ORDEMSERVICO" in schema["detected_entities"]["ordens_servico"]

    cliente_rows = [
        {
            "CODCLI": 10,
            "NOMECLI": "Duplicado",
            "CPF": "529.982.247-25",
            "CNPJ": "",
            "TELEFONE": "(47) 99999-9999",
            "CEP": "89200-000",
            "ENDERECO": "Rua Velha 40",
            "CIDADE": "Joinville",
            "ESTADO": "SC",
        },
        {"CODCLI": 11, "NOMECLI": "", "CPF": "111", "CNPJ": "", "TELEFONE": "", "CEP": "", "ENDERECO": "", "CIDADE": "", "ESTADO": ""},
        {
            "CODCLI": 12,
            "NOMECLI": "Nova Pessoa",
            "CPF": "",
            "CNPJ": "",
            "TELEFONE": "47 98888-7777",
            "CEP": "89201000",
            "ENDERECO": "Rua Nova, 55",
            "CIDADE": "Joinville",
            "ESTADO": "SC",
        },
    ]
    produto_rows = [
        {"CODPROD": 1, "CODIGO": "DUP", "NOMEPROD": "Duplicada", "UNIDADE": "UN", "PRECUSTO": 10, "OBS": "x", "CATEGORIA": "Tela", "QUANTIDADE": 1, "PRECO": 20},
        {"CODPROD": 2, "CODIGO": "SEM", "NOMEPROD": "", "UNIDADE": "UN", "PRECUSTO": 1, "OBS": "", "CATEGORIA": "", "QUANTIDADE": 0, "PRECO": 0},
        {"CODPROD": 3, "CODIGO": "NOVO", "NOMEPROD": "Fonte", "UNIDADE": "UN", "PRECUSTO": 40, "OBS": "", "CATEGORIA": "Energia", "QUANTIDADE": "4", "PRECO": 60},
    ]
    os_rows = [
        {
            "CODOS": 100,
            "CODCLI": 999,
            "EQUIPAMENTO": "Tablet",
            "IDENTIFICADOR": "SN1",
            "MARCAMODELO": "Apple - iPad",
            "TIPO": "",
            "OCORRENCIA": "Nao liga",
            "OBS": "",
            "SOLUCAO": "",
            "DATA": datetime(2026, 2, 1, 10, 0, 0),
            "DATSAI": None,
            "GARANTIA": 30,
            "STATUS_NOME": "Em avaliacao",
            "TECNICO_NOME": "Tec",
            "VALOR": 100,
        },
        {
            "CODOS": 101,
            "CODCLI": 10,
            "EQUIPAMENTO": "Celular",
            "IDENTIFICADOR": "SN2",
            "MARCAMODELO": "Samsung/A10",
            "TIPO": "",
            "OCORRENCIA": "Tela quebrada",
            "OBS": "obs",
            "SOLUCAO": "",
            "DATA": datetime(2026, 1, 10, 9, 0, 0),
            "DATSAI": None,
            "GARANTIA": 90,
            "STATUS_NOME": "Finalizado entregue",
            "TECNICO_NOME": "Tec",
            "VALOR": 200,
        },
        {
            "CODOS": 102,
            "CODCLI": 12,
            "EQUIPAMENTO": "",
            "IDENTIFICADOR": "SN3",
            "MARCAMODELO": "Dell - XPS",
            "TIPO": "Notebook",
            "OCORRENCIA": "Sem video",
            "OBS": "Cliente aguardando",
            "SOLUCAO": "Trocar fonte",
            "DATA": datetime(2026, 3, 1, 8, 0, 0),
            "DATSAI": datetime(2026, 3, 5, 8, 0, 0),
            "GARANTIA": 120,
            "STATUS_NOME": "Em manutencao",
            "TECNICO_NOME": "Tecnico CPlus",
            "VALOR": Decimal("350.50"),
        },
    ]
    monkeypatch.setattr(importer, "inspect_schema", lambda: {"tables": schema_tables})
    monkeypatch.setattr(importer, "test_connection", lambda: {"success": True, "driver": "fake", "table_count": 11})
    monkeypatch.setattr(importer, "_scalar", lambda sql, params=(): 3)

    row_importer = CPlusFirebirdImporter(FirebirdCredentials("fake.fdb"))
    monkeypatch.setattr(row_importer, "_rows", lambda sql, params=(): [{"sql": sql.strip().split()[1]}])
    assert row_importer._cliente_rows()
    assert row_importer._produto_rows()
    assert row_importer._os_rows()

    monkeypatch.setattr(importer, "_cliente_rows", lambda: cliente_rows)
    monkeypatch.setattr(importer, "_produto_rows", lambda: produto_rows)
    monkeypatch.setattr(importer, "_os_rows", lambda: os_rows)

    assert importer._split_address(None) == (None, None, None)
    assert importer._split_address("Sem numero") == ("Sem numero", None, "Numero da casa nao separado com seguranca.")
    assert importer._map_cliente({"CODCLI": 1, "NOMECLI": "X", "CPF": "111", "CNPJ": "222", "ENDERECO": ""})["cpf"] is None
    assert importer._map_produto({"PRECUSTO": 0, "PRECO": 20, "CODPROD": 1, "NOMEPROD": "Servico"})["margem"] == 0
    with app.app_context():
        db.session.add(Cliente(nome="Empresa CNPJ", cnpj="04252011000110", organization_id=1))
        db.session.commit()
        assert importer._cliente_duplicate({"cnpj": "04252011000110"})[1] == "CNPJ ja existe"
        assert importer._cliente_duplicate({"nome": "Duplicado", "telefone": "47999999999"})[1] == "nome + telefone ja existem"
        assert importer._produto_duplicate({"nome": "Duplicada"})[1] == "nome ja existe"
        assert importer._os_duplicate({"cliente": None})[1] == "cliente ausente"
    assert importer._status_zokyo("orcamento") == "aguardando_aprovacao"
    assert importer._status_zokyo("pronto retirada") == "pronto"
    assert importer._status_zokyo("teste tecnico") == "em_analise"
    assert importer._status_zokyo("aberto") == "recepcao"
    assert importer._split_marca_modelo("") == (None, None)
    assert importer._split_marca_modelo("Modelo Unico") == (None, "Modelo Unico")
    importer._write_log("fora", {}, {}, {}, {})

    with app.app_context():
        preview = importer.preview()
        assert preview["counts"] == {"clientes": 3, "produtos": 3, "ordens_servico": 3}
        assert preview["invalid_records"]["clientes"][0]["reason"] == "nome vazio"
        assert preview["invalid_records"]["ordens_servico"][0]["source_id"] == "100"
        assert preview["probable_duplicates"]["clientes"][0]["reason"] == "CPF ja existe"
        assert preview["probable_duplicates"]["produtos"][0]["reason"] == "codigo ja existe"
        assert preview["probable_duplicates"]["ordens_servico"][0]["reason"] == "OS semelhante ja existe"
        assert preview["examples"]["ordens_servico"][0]["cliente"] is None
        assert "Commit exige usuario admin" in preview["manual_confirmation"][3]

        with pytest.raises(CPlusImportError, match="Usuario admin"):
            importer.commit(admin_user="Admin")
        result = importer.commit(admin_user="Admin", admin_user_id=admin_id)
        assert result["created"] == {"clientes": 1, "produtos": 1, "ordens_servico": 1}
        assert result["skipped"] == {"clientes": 2, "produtos": 2, "ordens_servico": 2}
        assert Cliente.query.filter_by(nome="Nova Pessoa").count() == 1
        assert Peca.query.filter_by(codigo="NOVO").count() == 1
        imported_order = OrdemServico.query.filter_by(numero_serie="SN3").one()
        assert imported_order.status == "em_reparo"
        assert imported_order.tecnico_nome == "Tecnico CPlus"

        logs = list((tmp_path / "import_logs").glob("cplus_import_*.json"))
        assert logs
        payload = json.loads(logs[-1].read_text(encoding="utf-8"))
        assert payload["created"]["ordens_servico"] == 1

        failing = CPlusFirebirdImporter(FirebirdCredentials(str(tmp_path / "falha.fdb")))
        monkeypatch.setattr(failing, "preview", lambda: {"selected_tables": [], "counts": {}})
        monkeypatch.setattr(failing, "_cliente_rows", lambda: (_ for _ in ()).throw(RuntimeError("falha commit")))
        monkeypatch.setattr(failing, "_produto_rows", lambda: [])
        monkeypatch.setattr(failing, "_os_rows", lambda: [])
        with pytest.raises(RuntimeError, match="falha commit"):
            failing.commit(admin_user="Admin", admin_user_id=admin_id)
