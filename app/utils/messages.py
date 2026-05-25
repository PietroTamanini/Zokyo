"""
utils/messages.py
-----------------
Mensagens padronizadas para toda a aplicação.

Centralizar aqui evita:
  - mensagens inconsistentes entre rotas
  - vazamento de informações sensíveis
  - duplicação de strings
"""

# ── Autenticação ──────────────────────────────────────────────────────────────

AUTH_INVALID           = "E-mail ou senha incorretos."      # genérico: não revela qual campo
AUTH_BLOCKED           = "Conta temporariamente bloqueada por excesso de tentativas."
AUTH_SESSION_EXPIRED   = "Sua sessão expirou. Faça login novamente."
AUTH_UNAUTHORIZED      = "Autenticação necessária."
AUTH_FORBIDDEN         = "Acesso negado: permissão insuficiente."

# ── Validação geral ───────────────────────────────────────────────────────────

REQUIRED               = "Campo obrigatório: {campo}."
TOO_SHORT              = "{campo} deve ter pelo menos {min} caracteres."
TOO_LONG               = "{campo} deve ter no máximo {max} caracteres."
INVALID_FORMAT         = "{campo} com formato inválido."
INVALID_VALUE          = "Valor inválido para {campo}."
NEGATIVE_NOT_ALLOWED   = "{campo} não pode ser negativo."
MUST_BE_POSITIVE       = "{campo} deve ser maior que zero."
OUT_OF_RANGE           = "{campo} fora do intervalo permitido ({min}–{max})."
EMPTY_NOT_ALLOWED      = "{campo} não pode ser vazio ou apenas espaços."

# ── Documentos ────────────────────────────────────────────────────────────────

CPF_INVALID            = "CPF inválido."
CNPJ_INVALID           = "CNPJ inválido."
CEP_INVALID            = "CEP inválido. Use o formato 00000-000."
PHONE_INVALID          = "Telefone inválido. Use DDD + número (ex: 47 99999-9999)."
EMAIL_INVALID          = "E-mail inválido."
EMAIL_DUPLICATE        = "Este e-mail já está em uso."

# ── Senha ─────────────────────────────────────────────────────────────────────

PASSWORD_TOO_SHORT     = "Senha deve ter pelo menos 8 caracteres."
PASSWORD_NO_UPPER      = "Senha deve conter ao menos 1 letra maiúscula."
PASSWORD_NO_LOWER      = "Senha deve conter ao menos 1 letra minúscula."
PASSWORD_NO_DIGIT      = "Senha deve conter ao menos 1 número."
PASSWORD_NO_SPECIAL    = "Senha deve conter ao menos 1 caractere especial (!@#$%...)."
PASSWORD_TOO_COMMON    = "Senha muito comum. Escolha uma senha mais segura."
PASSWORD_MISMATCH      = "Confirmação de senha não confere."
PASSWORD_WRONG         = "Senha atual incorreta."

# ── CRUD genérico ─────────────────────────────────────────────────────────────

CREATED                = "{entity} criado(a) com sucesso."
UPDATED                = "{entity} atualizado(a) com sucesso."
DELETED                = "{entity} removido(a)."
NOT_FOUND              = "{entity} não encontrado(a)."
CONFLICT               = "{entity} já existe com este {campo}."

# ── Negócio específico ────────────────────────────────────────────────────────

OS_HAS_ACTIVE          = "Cliente possui {n} OS ativa(s). Encerre as OS antes de remover."
STOCK_INSUFFICIENT     = "Estoque insuficiente. Disponível: {disponivel}."
INVALID_STATUS         = "Status inválido. Valores aceitos: {valores}."
INVALID_NIVEL          = "Perfil inválido. Valores aceitos: {valores}."
SELF_DELETE_DENIED     = "Não é possível remover seu próprio usuário."

# ── Uploads ───────────────────────────────────────────────────────────────────

FILE_TOO_LARGE         = "Arquivo excede o tamanho máximo de {max_mb} MB."
FILE_TYPE_INVALID      = "Tipo de arquivo não permitido. Aceitos: {tipos}."
FILE_UNSAFE            = "Arquivo rejeitado por motivo de segurança."

# ── Sistema ───────────────────────────────────────────────────────────────────

INTERNAL_ERROR         = "Erro interno. Tente novamente ou contate o suporte."
RATE_LIMITED           = "Muitas requisições. Aguarde {secs}s."
CSRF_FAILED            = "Token de segurança inválido ou expirado. Recarregue a página."


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt(template: str, **kwargs) -> str:
    """Formata um template de mensagem com os parâmetros fornecidos."""
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def error_response(message: str, errors: dict | None = None,
                   code: int = 400) -> tuple:
    """
    Retorna tupla (dict, status_code) com formato padronizado de erro.

    Exemplo:
        return error_response("E-mail inválido", code=400)
        → ({"success": False, "erro": "E-mail inválido"}, 400)
    """
    from flask import jsonify
    body: dict = {"success": False, "erro": message}
    if errors:
        body["errors"] = errors
    return jsonify(body), code


def success_response(data=None, message: str = "", code: int = 200) -> tuple:
    """
    Retorna tupla (dict, status_code) com formato padronizado de sucesso.

    Exemplo:
        return success_response(cliente.to_dict(), code=201)
    """
    from flask import jsonify
    if data is not None:
        return jsonify(data), code
    body: dict = {"success": True}
    if message:
        body["mensagem"] = message
    return jsonify(body), code
