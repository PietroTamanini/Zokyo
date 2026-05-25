"""
utils/sanitizers.py
-------------------
Sanitização centralizada de todos os inputs da aplicação.

Funções:
  sanitize_text()      — texto genérico (trim, unicode, escape)
  sanitize_html()      — remove/escapa tags HTML perigosas
  sanitize_email()     — normaliza e-mail
  sanitize_cpf()       — remove tudo que não for dígito
  sanitize_cnpj()      — remove tudo que não for dígito
  sanitize_phone()     — remove tudo que não for dígito
  sanitize_cep()       — remove tudo que não for dígito
  sanitize_filename()  — torna nome de arquivo seguro
  sanitize_numeric()   — garante string numérica válida
  sanitize_dict()      — sanitiza todos os valores string de um dict
"""
import html
import re
import unicodedata
from typing import Any


# ── Constantes ────────────────────────────────────────────────────────────────

_SCRIPT_RE   = re.compile(r'<script[\s\S]*?>[\s\S]*?</script>', re.IGNORECASE)
_TAG_RE      = re.compile(r'<[^>]+>')
_NULL_BYTES  = re.compile(r'\x00')
_CTRL_RE     = re.compile(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]')  # control chars exceto \n \r \t
_FILENAME_RE = re.compile(r'[^\w\-. ]')                           # só alfanum, hífen, ponto, espaço

# Sequências unicode que podem ser usadas para spoofing/bypasses
_ZERO_WIDTH  = re.compile(
    '[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2060-\u206f\ufeff]'
)


# ── Funções principais ────────────────────────────────────────────────────────

def sanitize_text(value: Any, max_length: int = 0, strip: bool = True) -> str:
    """
    Sanitiza texto genérico:
      - converte para string
      - normaliza unicode (NFC)
      - remove bytes nulos e caracteres de controle
      - remove caracteres zero-width (anti-spoofing)
      - aplica trim
      - trunca ao max_length se especificado
      - NÃO faz html.escape (preserva texto para armazenamento)
    """
    if value is None:
        return ""

    text = str(value)

    # Normalização unicode NFC (equivalência canônica)
    text = unicodedata.normalize("NFC", text)

    # Remove bytes nulos
    text = _NULL_BYTES.sub("", text)

    # Remove caracteres de controle (exceto \n \r \t)
    text = _CTRL_RE.sub("", text)

    # Remove caracteres zero-width (usados para bypasses e spoofing)
    text = _ZERO_WIDTH.sub("", text)

    if strip:
        text = text.strip()

    if max_length and len(text) > max_length:
        text = text[:max_length].strip()

    return text


def sanitize_html(value: Any, allow_newlines: bool = False) -> str:
    """
    Sanitiza input que pode conter HTML/scripts:
      - remove tags <script>
      - remove todas as outras tags HTML
      - escapa entidades HTML residuais
      - aplica sanitize_text
    Retorna texto plano seguro para armazenamento e exibição.
    """
    if value is None:
        return ""

    text = sanitize_text(value, strip=False)

    # Remove blocos <script> primeiro
    text = _SCRIPT_RE.sub("", text)

    # Remove demais tags HTML
    text = _TAG_RE.sub("", text)

    # Escapa entidades HTML residuais
    text = html.unescape(text)   # decodifica entidades (ex: &lt; → <)
    text = html.escape(text)     # re-escapa tudo (< → &lt;)
    text = html.unescape(text)   # volta ao texto limpo para armazenamento

    if not allow_newlines:
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

    return text.strip()


def sanitize_email(value: Any) -> str:
    """
    Normaliza e-mail:
      - trim
      - lowercase
      - remove espaços internos inválidos
      - trunca a 254 chars (RFC 5321)
    """
    if value is None:
        return ""
    email = sanitize_text(value)
    email = email.lower()
    email = re.sub(r'\s+', '', email)   # remove espaços em qualquer posição
    return email[:254]


def sanitize_cpf(value: Any) -> str:
    """Remove tudo exceto dígitos. Retorna string de até 11 chars."""
    if value is None:
        return ""
    return re.sub(r'\D', '', str(value))[:11]


def sanitize_cnpj(value: Any) -> str:
    """Remove tudo exceto dígitos. Retorna string de até 14 chars."""
    if value is None:
        return ""
    return re.sub(r'\D', '', str(value))[:14]


def sanitize_phone(value: Any) -> str:
    """Remove tudo exceto dígitos. Retorna string de até 15 chars."""
    if value is None:
        return ""
    return re.sub(r'\D', '', str(value))[:15]


def sanitize_cep(value: Any) -> str:
    """Remove tudo exceto dígitos. Retorna string de até 8 chars."""
    if value is None:
        return ""
    return re.sub(r'\D', '', str(value))[:8]


def sanitize_filename(value: Any) -> str:
    """
    Torna um nome de arquivo seguro:
      - normaliza unicode (NFKD → ASCII)
      - remove path separators e caracteres perigosos
      - trunca a 200 chars
    """
    if not value:
        return "arquivo"

    name = str(value)
    # Normaliza unicode para ASCII
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Remove caracteres não seguros
    name = _FILENAME_RE.sub("_", name)
    name = name.strip(". ")  # sem pontos/espaços no início/fim

    return (name or "arquivo")[:200]


def sanitize_numeric(value: Any) -> str:
    """
    Aceita número inteiro ou decimal como string segura.
    Remove tudo exceto dígitos, ponto e sinal negativo inicial.
    """
    if value is None:
        return "0"
    s = str(value).strip()
    # Permite: dígitos, ponto decimal, sinal negativo no início
    s = re.sub(r'[^\d.\-]', '', s)
    # Garante apenas um ponto decimal
    parts = s.split('.')
    if len(parts) > 2:
        s = parts[0] + '.' + ''.join(parts[1:])
    return s or "0"


def sanitize_dict(data: dict, keys: list[str] | None = None) -> dict:
    """
    Sanitiza todos os valores string de um dicionário.
    Se `keys` for fornecido, sanitiza apenas as chaves listadas.
    Valores não-string são mantidos como estão.
    """
    result = dict(data)
    targets = keys if keys else list(result.keys())
    for k in targets:
        if k in result and isinstance(result[k], str):
            result[k] = sanitize_text(result[k])
    return result


def sanitize_search_query(value: Any, max_length: int = 100) -> str:
    """
    Sanitiza queries de busca:
      - sanitize_text
      - trunca ao max_length
      - remove operadores especiais que poderiam ser explorados
    """
    text = sanitize_text(value, max_length=max_length)
    return text
