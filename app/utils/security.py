"""
utils/security.py
-----------------
Helpers de segurança reutilizáveis.

Inclui:
  - Geração de tokens seguros
  - Validação de origens/referrers
  - Proteção contra Mass Assignment
  - Helpers de auditoria
"""
import hashlib
import hmac
import os
import secrets
from typing import Any


# ── Tokens seguros ────────────────────────────────────────────────────────────

def gerar_token(length: int = 32) -> str:
    """Gera token URL-safe criptograficamente seguro."""
    return secrets.token_urlsafe(length)


def gerar_token_hex(length: int = 32) -> str:
    """Gera token hexadecimal criptograficamente seguro."""
    return secrets.token_hex(length)


def gerar_uuid_filename(extensao: str) -> str:
    """
    Gera nome de arquivo único e seguro.
    Ex: gerar_uuid_filename('.pdf') → 'a3f7b2c1d4e5f6a7.pdf'
    """
    ext = extensao.lower().lstrip(".")
    return f"{secrets.token_hex(16)}.{ext}"


# ── Comparação segura ─────────────────────────────────────────────────────────

def compare_safe(a: str, b: str) -> bool:
    """
    Comparação de strings resistente a timing attack.
    Use em vez de '==' para tokens e senhas.
    """
    return hmac.compare_digest(
        a.encode("utf-8") if isinstance(a, str) else a,
        b.encode("utf-8") if isinstance(b, str) else b,
    )


# ── Mass Assignment Protection ────────────────────────────────────────────────

def filter_allowed(data: dict, allowed: list[str]) -> dict:
    """
    Filtra um dicionário mantendo apenas as chaves permitidas.
    Protege contra Mass Assignment — nunca use setattr() sem este filtro.

    Exemplo:
        safe = filter_allowed(request_data, ['nome', 'email', 'telefone'])
    """
    return {k: v for k, v in data.items() if k in allowed}


def apply_allowed(model_obj: Any, data: dict, allowed: list[str]) -> None:
    """
    Aplica apenas campos permitidos a um objeto de modelo ORM.
    Substitui o padrão inseguro:
        for campo in campos: setattr(obj, campo, data[campo])

    Uso:
        apply_allowed(cliente, data, ['nome', 'email', 'telefone'])
    """
    for campo in allowed:
        if campo in data:
            setattr(model_obj, campo, data[campo])


# ── Upload security ───────────────────────────────────────────────────────────

# Extensões permitidas por categoria
EXTENSOES_IMAGEM      = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
EXTENSOES_DOCUMENTO   = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt"}
EXTENSOES_PERMITIDAS  = EXTENSOES_IMAGEM | EXTENSOES_DOCUMENTO

# Extensões bloqueadas (executáveis e scripts)
EXTENSOES_BLOQUEADAS  = {
    "exe", "bat", "cmd", "sh", "ps1", "vbs", "js", "jar",
    "msi", "dll", "so", "php", "py", "rb", "pl", "asp", "aspx",
    "cgi", "htaccess", "htpasswd", "config", "ini",
}

# MIME types seguros (whitelist)
MIME_PERMITIDOS = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv",
}

MAX_UPLOAD_MB  = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def validar_upload(filename: str, mime_type: str,
                   tamanho_bytes: int) -> list[str]:
    """
    Valida um arquivo de upload.
    Retorna lista de erros (vazia = arquivo aceito).
    """
    erros = []

    if not filename:
        erros.append("Nome de arquivo ausente.")
        return erros

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in EXTENSOES_BLOQUEADAS:
        erros.append(f"Tipo de arquivo bloqueado: .{ext}")

    if ext not in EXTENSOES_PERMITIDAS:
        erros.append(
            f"Extensão não permitida: .{ext}. "
            f"Aceitas: {', '.join(sorted(EXTENSOES_PERMITIDAS))}"
        )

    if mime_type and mime_type not in MIME_PERMITIDOS:
        erros.append(f"Tipo MIME não permitido: {mime_type}")

    if tamanho_bytes > MAX_UPLOAD_BYTES:
        erros.append(
            f"Arquivo muito grande: {tamanho_bytes / 1024 / 1024:.1f} MB. "
            f"Máximo: {MAX_UPLOAD_MB} MB"
        )

    # Verificação de path traversal
    import os
    safe = os.path.basename(filename)
    if safe != filename.replace("/", "").replace("\\", ""):
        erros.append("Nome de arquivo contém caminho inválido.")

    return erros


# ── Hash de dados sensíveis (para logs) ───────────────────────────────────────

def hash_for_log(value: str) -> str:
    """
    Retorna hash SHA-256 truncado de um valor para uso seguro em logs.
    Não loga o valor real de e-mails, CPFs, etc.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:12]


# ── Verificação de ambiente ───────────────────────────────────────────────────

def is_production() -> bool:
    """Verifica se o ambiente atual é produção."""
    return os.environ.get("FLASK_ENV", "").lower() == "production"
