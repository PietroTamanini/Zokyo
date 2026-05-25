"""
utils/exceptions.py
-------------------
Exceções customizadas para a aplicação Zokyo.

Hierarquia:
  AppError
    ├── ValidationError
    ├── AuthError
    │     ├── UnauthorizedError
    │     └── ForbiddenError
    ├── ApiError
    ├── SecurityError
    └── BusinessRuleError
"""


class AppError(Exception):
    """Base de todas as exceções da aplicação."""

    def __init__(self, message: str, code: int = 500):
        super().__init__(message)
        self.message = message
        self.code    = code

    def to_dict(self) -> dict:
        return {"success": False, "erro": self.message}


class ValidationError(AppError):
    """
    Dados de entrada inválidos (400).
    Pode carregar um mapa campo→erros.
    """

    def __init__(self, message: str, errors: dict | None = None):
        super().__init__(message, code=400)
        self.errors = errors or {}

    def to_dict(self) -> dict:
        d = super().to_dict()
        if self.errors:
            d["errors"] = self.errors
        return d


class AuthError(AppError):
    """Erro base de autenticação/autorização."""
    pass


class UnauthorizedError(AuthError):
    """Usuário não autenticado (401)."""

    def __init__(self, message: str = "Autenticação necessária."):
        super().__init__(message, code=401)


class ForbiddenError(AuthError):
    """Usuário autenticado mas sem permissão (403)."""

    def __init__(self, message: str = "Acesso negado."):
        super().__init__(message, code=403)


class ApiError(AppError):
    """Erro genérico de API."""
    pass


class SecurityError(AppError):
    """
    Erro de segurança — CSRF, injeção, etc. (400/403).
    Registrado com nível WARNING no log.
    """

    def __init__(self, message: str = "Requisição bloqueada por segurança.",
                 code: int = 400):
        super().__init__(message, code=code)


class BusinessRuleError(AppError):
    """Violação de regra de negócio (422)."""

    def __init__(self, message: str):
        super().__init__(message, code=422)


class NotFoundError(AppError):
    """Recurso não encontrado (404)."""

    def __init__(self, message: str = "Recurso não encontrado."):
        super().__init__(message, code=404)


class ConflictError(AppError):
    """Conflito de dados — duplicidade (409)."""

    def __init__(self, message: str):
        super().__init__(message, code=409)
