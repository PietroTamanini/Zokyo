from .auth import auth_bp
from .clientes import clientes_bp
from .defeitos_padrao import defeitos_bp
from .fornecedores import fornecedores_bp
from .health import health_bp
from .importacao import importacao_bp
from .laudos import laudos_bp
from .os import os_bp
from .pages import pages_bp
from .pecas import pecas_bp
from .platform import platform_bp
from .portal import portal_bp
from .privacy import privacy_bp
from .relatorios import relatorios_bp
from .transacoes import transacoes_bp
from .usuarios import usuarios_bp

__all__ = [
    "auth_bp", "pages_bp", "clientes_bp", "os_bp",
    "pecas_bp", "fornecedores_bp", "transacoes_bp",
    "usuarios_bp", "defeitos_bp", "importacao_bp", "laudos_bp", "health_bp", "portal_bp", "relatorios_bp", "platform_bp", "privacy_bp",
]
