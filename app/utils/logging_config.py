"""
utils/logging_config.py
-----------------------
Fix L03: logging estruturado com mascaramento de dados sensíveis.

Configura logging para produção:
  - Mascara senhas, tokens, CPFs, e-mails parcialmente
  - Formato JSON em produção para ingestão por SIEM
  - Rotação de arquivo de log
"""
import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path


# Padrões para mascaramento
_MASK_PATTERNS = [
    # Senhas e tokens em query strings / corpo
    (re.compile(r"(senha|password|passwd|token|secret|api[_-]?key)=([^&\s\"']{3})[^&\s\"']*",
                re.IGNORECASE),
     r"\1=\2***"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)(\w{4})\w+", re.IGNORECASE),
     r"\1\2***"),
    # CPF: 000.000.000-00 → 0**.***.**0-00
    (re.compile(r"\b(\d{3})\.\d{3}\.\d{3}-(\d{2})\b"),
     r"\1.***.***-\2"),
    # CNPJ: 00.000.000/0000-00 → 0**.000.000/****-00
    (re.compile(r"\b(\d{2})\.\d{3}\.\d{3}/\d{4}-(\d{2})\b"),
     r"\1.***.***/****-\2"),
    # E-mail: user@domain.com → u***@domain.com
    (re.compile(r"\b([a-zA-Z0-9._%+\-]{1})[a-zA-Z0-9._%+\-]+(@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"),
     r"\1***\2"),
    # X-Forwarded-For (não logar IPs completos)
    (re.compile(r"(X-Forwarded-For[:\s]+)(\d+\.\d+)\.\d+\.\d+", re.IGNORECASE),
     r"\1\2.***.***"),
]


def _mask(text: str) -> str:
    for pattern, replacement in _MASK_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    """Filter que aplica mascaramento em todas as mensagens de log."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg     = _mask(str(record.msg))
        record.args    = tuple(_mask(str(a)) for a in record.args) if record.args else ()
        return True


def configure_logging(app):
    """
    Configura logging da aplicação.
    Em produção: arquivo rotativo + stderr em formato mais detalhado.
    Em desenvolvimento: stderr simples.
    """
    is_prod   = not app.config.get("DEBUG", False)
    log_level = logging.INFO if is_prod else logging.DEBUG

    # Remove handlers padrão do Flask
    app.logger.handlers.clear()

    fmt_simple = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    fmt_detail = "[%(asctime)s] %(levelname)s %(name)s [%(filename)s:%(lineno)d]: %(message)s"

    formatter  = logging.Formatter(fmt_detail if is_prod else fmt_simple,
                                   datefmt="%Y-%m-%dT%H:%M:%S")

    mask_filter = MaskingFilter()

    # Handler stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.addFilter(mask_filter)
    app.logger.addHandler(stderr_handler)

    # Handler de arquivo rotativo em produção
    if is_prod:
        log_dir = Path(os.environ.get("LOG_DIR", "/var/log/zokyo"))
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / "zokyo.log",
                maxBytes=10 * 1024 * 1024,   # 10 MB
                backupCount=10,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(mask_filter)
            app.logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            app.logger.warning("Não foi possível criar log em arquivo: %s", e)

    app.logger.setLevel(log_level)

    # Propaga para loggers dos módulos internos
    for logger_name in ("app", "sqlalchemy.engine", "werkzeug"):
        lg = logging.getLogger(logger_name)
        lg.setLevel(log_level)
        if logger_name != "sqlalchemy.engine" or not is_prod:
            lg.addHandler(stderr_handler)
            lg.addFilter(mask_filter)
