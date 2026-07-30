from datetime import datetime, timedelta
from io import BytesIO
from unicodedata import normalize

from flask import Blueprint, Flask

from app.utils import auth, request_data, sanitizers, security, validators
from app.utils.exceptions import (
    ApiError,
    AppError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    SecurityError,
    UnauthorizedError,
    ValidationError,
)


def _plain(value: str) -> str:
    return normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def _plain_list(values: list[str]) -> list[str]:
    return [_plain(item) for item in values]


def test_validar_email_cobre_casos_principais():
    assert validators.validar_email("Usuario+tag@Sub.Example.com") is True
    assert validators.validar_email(None) is False
    assert validators.validar_email("a@b.c") is False
    assert validators.validar_email("x" * 250 + "@a.com") is False
    assert validators.validar_email("a@@example.com") is False
    assert validators.validar_email("@example.com") is False
    assert validators.validar_email("user@") is False
    assert validators.validar_email("user@example") is False
    assert validators.validar_email("user example.com") is False


def test_validar_documentos_cpf_cnpj():
    assert validators.validar_cpf("529.982.247-25") is True
    assert validators.validar_cpf("11111111111") is False
    assert validators.validar_cpf("52998224715") is False
    assert validators.validar_cpf("52998224724") is False
    assert validators.validar_cpf("123") is False

    assert validators.validar_cnpj("04.252.011/0001-10") is True
    assert validators.validar_cnpj("11111111111111") is False
    assert validators.validar_cnpj("04252011000120") is False
    assert validators.validar_cnpj("04252011000111") is False
    assert validators.validar_cnpj("123") is False

    assert validators.validar_cpf_cnpj("") == (True, None, None, "")
    assert validators.validar_cpf_cnpj("52998224725") == (True, "52998224725", None, "")
    assert validators.validar_cpf_cnpj("52998224724")[3] == "CPF inválido."
    assert validators.validar_cpf_cnpj("04252011000110") == (True, None, "04252011000110", "")
    assert validators.validar_cpf_cnpj("04252011000111")[3] == "CNPJ inválido."
    assert validators.validar_cpf_cnpj("123")[3] == "CPF/CNPJ deve ter 11 ou 14 dígitos."


def test_validar_telefone_cep_texto_numero_data_enum_uf():
    assert validators.validar_telefone("") is True
    assert validators.validar_telefone("", obrigatorio=True) is False
    assert validators.validar_telefone("+55 (47) 99999-9999") is True
    assert validators.validar_telefone("(47) 3333-3333") is True
    assert validators.validar_telefone("123") is False
    assert validators.validar_telefone("(10) 99999-9999") is False
    assert validators.validar_telefone("(47) 89999-9999") is False
    assert validators.validar_telefone("(47) 1333-3333") is False

    assert validators.validar_cep("") is True
    assert validators.validar_cep("", obrigatorio=True) is False
    assert validators.validar_cep("89000-000") is True
    assert validators.validar_cep("00000-000") is False
    assert validators.validar_cep("123") is False

    assert _plain_list(validators.validar_texto("", "Nome")) == ["Nome e obrigatorio."]
    assert validators.validar_texto("", "Nome", obrigatorio=False) == []
    assert validators.validar_texto("ab", "Nome", minimo=3) == ["Nome deve ter pelo menos 3 caracteres."]
    assert _plain_list(validators.validar_texto("abcd", "Nome", maximo=3)) == [
        "Nome deve ter no maximo 3 caracteres."
    ]
    assert validators.validar_texto("abc", "Nome", minimo=2, maximo=4) == []

    assert _plain_list(validators.validar_numero(None, "Valor")) == ["Valor e obrigatorio."]
    assert validators.validar_numero("", "Valor", obrigatorio=False) == []
    assert _plain_list(validators.validar_numero("abc", "Valor")) == ["Valor deve ser um numero valido."]
    assert _plain_list(validators.validar_numero("nan", "Valor")) == ["Valor deve ser um numero finito."]
    assert _plain_list(validators.validar_numero("-1", "Valor", minimo=0)) == ["Valor nao pode ser menor que 0."]
    assert _plain_list(validators.validar_numero("11", "Valor", maximo=10)) == ["Valor nao pode ser maior que 10."]
    assert validators.validar_numero("5", "Valor", tipo=int, minimo=1, maximo=10) == []

    ontem = (datetime.now() - timedelta(days=1)).date().isoformat()
    amanha = (datetime.now() + timedelta(days=1)).date().isoformat()
    assert validators.validar_data("", "Data") == []
    assert _plain_list(validators.validar_data("", "Data", obrigatorio=True)) == [
        "Data e obrigatoria."
    ]
    assert _plain_list(validators.validar_data("invalida", "Data")) == [
        "Data com formato invalido. Use AAAA-MM-DD."
    ]
    assert _plain_list(validators.validar_data(ontem, "Data", permitir_passado=False)) == [
        "Data nao pode ser uma data passada."
    ]
    assert _plain_list(validators.validar_data(amanha, "Data", permitir_futuro=False)) == [
        "Data nao pode ser uma data futura."
    ]

    assert _plain_list(validators.validar_enum("", {"a"}, "Tipo")) == ["Tipo e obrigatorio."]
    assert validators.validar_enum("", {"a"}, "Tipo", obrigatorio=False) == []
    assert _plain_list(validators.validar_enum("b", {"a"}, "Tipo")) == ["Tipo invalido. Valores aceitos: a."]
    assert validators.validar_enum("a", {"a"}, "Tipo") == []
    assert validators.validar_uf("") is True
    assert validators.validar_uf("", obrigatorio=True) is False
    assert validators.validar_uf("sc") is True
    assert validators.validar_uf("XX") is False


def test_sanitizers_cobrem_normalizacao_e_limites():
    assert sanitizers.sanitize_text(None) == ""
    assert sanitizers.sanitize_text("  A\x00B\x01\u200b  ") == "AB"
    assert sanitizers.sanitize_text("  abc  ", strip=False) == "  abc  "
    assert sanitizers.sanitize_text("abcdef", max_length=3) == "abc"

    assert sanitizers.sanitize_html(None) == ""
    assert sanitizers.sanitize_html("<script>x()</script><b>Ola</b>\nMundo") == "Ola Mundo"
    assert sanitizers.sanitize_html("A\nB", allow_newlines=True) == "A\nB"

    assert sanitizers.sanitize_email(None) == ""
    assert sanitizers.sanitize_email(" User @Example.COM ") == "user@example.com"
    assert len(sanitizers.sanitize_email("A" * 300)) == 254
    assert sanitizers.sanitize_cpf(None) == ""
    assert sanitizers.sanitize_cpf("529.982.247-25") == "52998224725"
    assert sanitizers.sanitize_cnpj(None) == ""
    assert sanitizers.sanitize_cnpj("04.252.011/0001-10") == "04252011000110"
    assert sanitizers.sanitize_cpf_cnpj(None) == ""
    assert sanitizers.sanitize_cpf_cnpj("04.252.011/0001-10") == "04252011000110"
    assert sanitizers.sanitize_phone(None) == ""
    assert sanitizers.sanitize_phone("+55 (47) 99999-9999") == "5547999999999"
    assert sanitizers.sanitize_cep(None) == ""
    assert sanitizers.sanitize_cep("89000-000") == "89000000"

    assert sanitizers.sanitize_filename(None) == "arquivo"
    assert sanitizers.sanitize_filename("á/bad?.pdf") == "a_bad_.pdf"
    assert sanitizers.sanitize_filename(". . ") == "arquivo"
    assert len(sanitizers.sanitize_filename("a" * 250 + ".txt")) == 200

    assert sanitizers.sanitize_numeric(None) == "0"
    assert sanitizers.sanitize_numeric("R$ -12.3x") == "-12.3"
    assert sanitizers.sanitize_numeric("1.2.3") == "1.23"
    assert sanitizers.sanitize_numeric("abc") == "0"

    assert sanitizers.sanitize_dict({"a": "  x  ", "b": 1}) == {"a": "x", "b": 1}
    assert sanitizers.sanitize_dict({"a": "  x  ", "b": "  y  "}, keys=["b"]) == {"a": "  x  ", "b": "y"}
    assert sanitizers.sanitize_search_query("  abc  ", max_length=2) == "ab"


def test_auth_password_policy_and_decorators():
    assert auth.validar_senha_forte("Senha!123") == []
    weak = auth.validar_senha_forte("abc")
    plain_weak = _plain_list(weak)
    assert "Minimo 8 caracteres." in plain_weak
    assert "Pelo menos 1 letra maiuscula." in plain_weak
    assert "Pelo menos 1 numero." in plain_weak
    assert "Pelo menos 1 caractere especial." in weak
    assert "Pelo menos 1 letra minuscula." in _plain_list(auth.validar_senha_forte("SENHA!123"))
    assert auth.validar_senha_forte("Password1!") == []
    assert "Senha muito comum. Escolha uma senha mais unica." in _plain_list(auth.validar_senha_forte("senha123"))

    app = Flask(__name__)
    app.secret_key = "test"
    auth_bp = Blueprint("auth", __name__)
    pages_bp = Blueprint("pages", __name__)

    @app.route("/api")
    @auth.api_login_required
    def api_route():
        return {"ok": True}

    @app.route("/api-admin")
    @auth.nivel_required("admin")
    def api_admin():
        return {"ok": True}

    @app.route("/page")
    @auth.page_nivel_required("admin")
    def page_route():
        return "ok"

    @auth_bp.route("/login")
    def login_page():
        return "login"

    @pages_bp.route("/")
    def dashboard():
        return "dash"

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)

    client = app.test_client()
    assert client.get("/api").status_code == 401
    assert client.get("/api-admin").status_code == 401
    assert client.get("/page").status_code == 302
    with client.session_transaction() as session:
        session["usuario_id"] = 1
        session["nivel"] = "consulta"
    assert client.get("/api").status_code == 200
    assert client.get("/api-admin").status_code == 403
    assert client.get("/page").status_code == 302
    with client.session_transaction() as session:
        session["nivel"] = "admin"
    assert client.get("/api-admin").status_code == 200
    assert client.get("/page").status_code == 200


def test_security_helpers_and_upload_validation(monkeypatch):
    assert len(security.gerar_token(8)) > 8
    assert len(security.gerar_token_hex(8)) == 16
    generated = security.gerar_uuid_filename(".PDF")
    assert generated.endswith(".pdf")
    assert security.compare_safe("a", "a") is True
    assert security.compare_safe(b"a", b"b") is False
    assert security.filter_allowed({"a": 1, "b": 2}, ["a"]) == {"a": 1}

    class Dummy:
        pass

    dummy = Dummy()
    security.apply_allowed(dummy, {"nome": "Teste", "admin": True}, ["nome"])
    assert dummy.nome == "Teste"
    assert not hasattr(dummy, "admin")

    assert security.validar_upload("", "text/plain", 1) == ["Nome de arquivo ausente."]
    assert security.validar_upload("script.exe", "text/plain", 1)
    assert security.validar_upload("arquivo.xyz", "text/plain", 1)
    assert security.validar_upload("arquivo.txt", "application/x-msdownload", 1)
    assert security.validar_upload("arquivo.txt", "text/plain", security.MAX_UPLOAD_BYTES + 1)
    assert security.validar_upload("../arquivo.txt", "text/plain", 1)
    assert security.validar_upload("arquivo.txt", "text/plain", 1) == []
    assert len(security.hash_for_log("valor-sensivel")) == 12
    monkeypatch.setenv("FLASK_ENV", "production")
    assert security.is_production() is True
    monkeypatch.setenv("FLASK_ENV", "development")
    assert security.is_production() is False


def test_request_data_sources():
    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/data", methods=["POST"])
    def data():
        payload, source = request_data.get_request_data()
        files = payload.pop("_files", None)
        return {"payload": payload, "source": source, "has_files": bool(files)}

    client = app.test_client()
    assert client.post("/data", json={"a": 1}).get_json() == {"payload": {"a": 1}, "source": "json", "has_files": False}
    assert client.post("/data", data={"a": "1"}).get_json() == {"payload": {"a": "1"}, "source": "form", "has_files": False}
    multipart = client.post("/data", data={"f": (BytesIO(b"x"), "a.txt"), "a": "1"})
    assert multipart.get_json() == {"payload": {"a": "1"}, "source": "multipart", "has_files": True}
    assert client.post("/data").get_json() == {"payload": {}, "source": "empty", "has_files": False}


def test_app_exceptions_to_dict_and_codes():
    assert AppError("erro").to_dict() == {"success": False, "erro": "erro"}
    assert ValidationError("invalido").to_dict() == {"success": False, "erro": "invalido"}
    assert ValidationError("invalido", {"nome": ["obrigatorio"]}).to_dict() == {
        "success": False,
        "erro": "invalido",
        "errors": {"nome": ["obrigatorio"]},
    }
    assert UnauthorizedError().code == 401
    assert ForbiddenError().code == 403
    assert SecurityError().code == 400
    assert SecurityError("bloqueado", code=403).code == 403
    assert BusinessRuleError("regra").code == 422
    assert NotFoundError().code == 404
    assert ConflictError("duplicado").code == 409
    assert ApiError("api", code=418).code == 418
