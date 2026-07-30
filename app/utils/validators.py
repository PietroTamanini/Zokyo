"""
utils/validators.py
-------------------
Validadores centralizados e reutilizáveis.

Cada função retorna True (válido) ou False (inválido).
Para validação com mensagem de erro, use os validators que retornam list[str].
"""
import re
from datetime import datetime
from typing import Optional

# ── Email ─────────────────────────────────────────────────────────────────────

# RFC 5322 simplificado — muito mais robusto que a regex anterior
# Aceita: usuario@dominio.tld, usuario+tag@sub.dominio.com.br
# Bloqueia: @dominio, usuario@, usuario.com, espaços
EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)


def validar_email(email: str) -> bool:
    """
    Valida e-mail com regex RFC robusta.
    - Requer usuário não vazio antes do @
    - Requer domínio com pelo menos um ponto
    - Requer TLD de pelo menos 2 letras
    - Bloqueia espaços, @ duplo, TLDs numéricos
    """
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    if len(email) < 6 or len(email) > 254:
        return False
    # Verifica exatamente 1 @
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    # Local e domínio não podem ser vazios
    if not local or not domain:
        return False
    # Domínio deve ter pelo menos um ponto e TLD com 2+ letras
    if "." not in domain:
        return False
    # Regex final
    return bool(EMAIL_RE.match(email))


# ── CPF ───────────────────────────────────────────────────────────────────────

def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def validar_cpf(cpf: str) -> bool:
    """
    Valida CPF com algoritmo oficial dos dígitos verificadores.
    - Aceita com ou sem formatação (pontos/traço)
    - Bloqueia sequências repetidas (ex: 11111111111)
    - Valida ambos os dígitos verificadores
    """
    d = _digitos(cpf)
    if len(d) != 11:
        return False
    # Bloqueia sequências repetidas
    if len(set(d)) == 1:
        return False
    # Primeiro dígito verificador
    soma = sum(int(d[i]) * (10 - i) for i in range(9))
    r1   = (soma * 10 % 11) % 10
    if r1 != int(d[9]):
        return False
    # Segundo dígito verificador
    soma = sum(int(d[i]) * (11 - i) for i in range(10))
    r2   = (soma * 10 % 11) % 10
    return r2 == int(d[10])


# ── CNPJ ──────────────────────────────────────────────────────────────────────

def validar_cnpj(cnpj: str) -> bool:
    """
    Valida CNPJ com algoritmo oficial dos dígitos verificadores.
    - Aceita com ou sem formatação
    - Bloqueia sequências repetidas (ex: 11111111111111)
    """
    d = _digitos(cnpj)
    if len(d) != 14:
        return False
    if len(set(d)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1  = sum(int(d[i]) * pesos1[i] for i in range(12))
    r1     = 0 if soma1 % 11 < 2 else 11 - soma1 % 11
    if r1 != int(d[12]):
        return False
    soma2 = sum(int(d[i]) * pesos2[i] for i in range(13))
    r2    = 0 if soma2 % 11 < 2 else 11 - soma2 % 11
    return r2 == int(d[13])


# ── Telefone ──────────────────────────────────────────────────────────────────

# DDDs válidos no Brasil (ANATEL)
_DDDS_VALIDOS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19,  # SP
    21, 22, 24,                            # RJ
    27, 28,                                # ES
    31, 32, 33, 34, 35, 37, 38,            # MG
    41, 42, 43, 44, 45, 46,                # PR
    47, 48, 49,                            # SC
    51, 53, 54, 55,                        # RS
    61,                                    # DF
    62, 64,                                # GO
    63,                                    # TO
    65, 66,                                # MT
    67,                                    # MS
    68,                                    # AC
    69,                                    # RO
    71, 73, 74, 75, 77,                    # BA
    79,                                    # SE
    81, 87,                                # PE
    82,                                    # AL
    83,                                    # PB
    84,                                    # RN
    85, 88,                                # CE
    86, 89,                                # PI
    91, 93, 94,                            # PA
    92, 97,                                # AM
    95,                                    # RR
    96,                                    # AP
    98, 99,                                # MA
}


def validar_cpf_cnpj(documento: str) -> tuple[bool, str | None, str | None, str]:
    """
    Valida documento opcional de cliente.

    Retorna: (valido, cpf, cnpj, mensagem)
    """
    d = _digitos(documento)
    if not d:
        return True, None, None, ""
    if len(d) == 11:
        if validar_cpf(d):
            return True, d, None, ""
        return False, None, None, "CPF inválido."
    if len(d) == 14:
        if validar_cnpj(d):
            return True, None, d, ""
        return False, None, None, "CNPJ inválido."
    return False, None, None, "CPF/CNPJ deve ter 11 ou 14 dígitos."


def validar_telefone(telefone: str, obrigatorio: bool = False) -> bool:
    """
    Valida telefone brasileiro.
    - Aceita formato com ou sem formatação
    - Valida DDD (lista oficial ANATEL)
    - Aceita fixo (8 dígitos) ou celular (9 dígitos, começa com 9)
    - Se obrigatorio=False e campo vazio, retorna True
    """
    if not telefone:
        return not obrigatorio

    digitos = _digitos(telefone)

    # Com ou sem código do país (55)
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]

    if len(digitos) not in (10, 11):
        return False

    ddd = int(digitos[:2])
    if ddd not in _DDDS_VALIDOS:
        return False

    numero = digitos[2:]
    # Celular: 9 dígitos começando com 9
    if len(numero) == 9 and numero[0] != "9":
        return False
    # Fixo: 8 dígitos começando com 2-8
    if len(numero) == 8 and numero[0] not in "2345678":
        return False

    return True


# ── CEP ───────────────────────────────────────────────────────────────────────

def validar_cep(cep: str, obrigatorio: bool = False) -> bool:
    """
    Valida CEP brasileiro.
    - Aceita 00000-000 ou 00000000
    - Exatamente 8 dígitos
    - Não pode ser 00000000
    """
    if not cep:
        return not obrigatorio

    digitos = _digitos(cep)
    if len(digitos) != 8:
        return False
    if digitos == "00000000":
        return False
    return True


# ── Textos ────────────────────────────────────────────────────────────────────

def validar_texto(
    valor: str,
    campo: str = "Campo",
    minimo: int = 1,
    maximo: int = 0,
    obrigatorio: bool = True,
) -> list[str]:
    """
    Valida campo de texto.
    Retorna lista de erros (vazia = válido).

    Args:
        valor:       Valor a validar
        campo:       Nome do campo para mensagens de erro
        minimo:      Comprimento mínimo (0 = sem mínimo)
        maximo:      Comprimento máximo (0 = sem máximo)
        obrigatorio: Se True, vazio/espaços é inválido
    """
    erros = []
    texto = (valor or "").strip()

    if not texto:
        if obrigatorio:
            erros.append(f"{campo} é obrigatório.")
        return erros

    if minimo and len(texto) < minimo:
        erros.append(f"{campo} deve ter pelo menos {minimo} caracteres.")

    if maximo and len(texto) > maximo:
        erros.append(f"{campo} deve ter no máximo {maximo} caracteres.")

    return erros


# ── Numérico ──────────────────────────────────────────────────────────────────

def validar_numero(
    valor,
    campo: str = "Valor",
    tipo: type = float,
    minimo: Optional[float] = None,
    maximo: Optional[float] = None,
    obrigatorio: bool = True,
) -> list[str]:
    """
    Valida campo numérico.
    Retorna lista de erros (vazia = válido).
    """
    erros = []

    if valor is None or str(valor).strip() == "":
        if obrigatorio:
            erros.append(f"{campo} é obrigatório.")
        return erros

    try:
        n = tipo(valor)
    except (ValueError, TypeError):
        erros.append(f"{campo} deve ser um número válido.")
        return erros

    import math
    if math.isnan(n) or math.isinf(n):
        erros.append(f"{campo} deve ser um número finito.")
        return erros

    if minimo is not None and n < minimo:
        erros.append(f"{campo} não pode ser menor que {minimo}.")

    if maximo is not None and n > maximo:
        erros.append(f"{campo} não pode ser maior que {maximo}.")

    return erros


# ── Datas ─────────────────────────────────────────────────────────────────────

def validar_data(
    valor: str,
    campo: str = "Data",
    permitir_passado: bool = True,
    permitir_futuro: bool = True,
    obrigatorio: bool = False,
) -> list[str]:
    """
    Valida campo de data (formato ISO: YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS).
    """
    erros = []

    if not valor or not str(valor).strip():
        if obrigatorio:
            erros.append(f"{campo} é obrigatória.")
        return erros

    try:
        dt = datetime.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        erros.append(f"{campo} com formato inválido. Use AAAA-MM-DD.")
        return erros

    agora = datetime.now()

    if not permitir_passado and dt.date() < agora.date():
        erros.append(f"{campo} não pode ser uma data passada.")

    if not permitir_futuro and dt.date() > agora.date():
        erros.append(f"{campo} não pode ser uma data futura.")

    return erros


# ── Enum/Whitelist ────────────────────────────────────────────────────────────

def validar_enum(
    valor: str,
    validos: set | list | tuple,
    campo: str = "Campo",
    obrigatorio: bool = True,
) -> list[str]:
    """
    Valida que um valor está dentro de um conjunto de opções válidas.
    """
    erros = []

    if not valor:
        if obrigatorio:
            erros.append(f"{campo} é obrigatório.")
        return erros

    if valor not in validos:
        erros.append(
            f"{campo} inválido. Valores aceitos: {', '.join(str(v) for v in validos)}."
        )

    return erros


# ── UF ────────────────────────────────────────────────────────────────────────

_UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def validar_uf(uf: str, obrigatorio: bool = False) -> bool:
    """Valida sigla de estado brasileiro."""
    if not uf:
        return not obrigatorio
    return str(uf).upper().strip() in _UFS_VALIDAS
