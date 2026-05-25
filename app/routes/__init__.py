from .auth            import auth_bp
from .pages           import pages_bp
from .clientes        import clientes_bp
from .os              import os_bp
from .pecas           import pecas_bp
from .fornecedores    import fornecedores_bp
from .transacoes      import transacoes_bp
from .usuarios        import usuarios_bp
from .defeitos_padrao import defeitos_bp

__all__ = [
    "auth_bp", "pages_bp", "clientes_bp", "os_bp",
    "pecas_bp", "fornecedores_bp", "transacoes_bp",
    "usuarios_bp", "defeitos_bp",
]
