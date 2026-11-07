"""
utils/logging_config.py
-----------------------
Fix L03: logging estruturado com mascaramento de dados sensíveis.

Configura logging para produção:
  - Remove senhas, tokens, documentos, e-mails e endereços IPv4 dos logs
  - Formato JSON em produção para ingestão por SIEM
  - Rotação de arquivo de log
"""
import json
import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path

from flask import g, has_request_context

# Padrões para mascaramento
_MASK_PATTERNS = [
    # Senhas e tokens em query strings / corpo
    (re.compile(r"(senha|password|passwd|token|secret|api[_-]?key)=([^&\s\"']+)",
                re.IGNORECASE),
     r"\1=[REDACTED]"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/-]+", re.IGNORECASE),
     r"\1[REDACTED]"),
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "[CPF]"),
    (re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"), "[CNPJ]"),
    (re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"), "[EMAIL]"),
    # IPv4 in exception messages, including X-Forwarded-For values.
    (re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
     "[IP]"),
]


def _mask(text: str) -> str:
    for pattern, replacement in _MASK_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class MaskingFilter(logging.Filter):
    """Attach request ID; formatters redact complete messages and tracebacks."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(g, "request_id", None) if has_request_context() else None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _mask(record.getMessage()),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exception"] = _mask(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=True)


class SafeTextFormatter(logging.Formatter):
    """Mask the rendered message and traceback in development logs."""

    def format(self, record):
        return _mask(super().format(record))


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
    app.logger.propagate = False

    fmt_simple = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    formatter = JsonFormatter() if is_prod else SafeTextFormatter(fmt_simple, datefmt="%Y-%m-%dT%H:%M:%S")

    mask_filter = MaskingFilter()

    # Handler stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler._zokyo_handler = True
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
            file_handler._zokyo_handler = True
            file_handler.setFormatter(formatter)
            file_handler.addFilter(mask_filter)
            app.logger.addHandler(file_handler)
        except (PermissionError, OSError) as e:
            app.logger.warning("Não foi possível criar log em arquivo: %s", e)

    app.logger.setLevel(log_level)

    # Modules under app.* inherit the Flask logger's filtered handlers.
    # Werkzeug/SQLAlchemy are separate trees and must not fall through to root.
    for logger_name in ("sqlalchemy.engine", "werkzeug"):
        lg = logging.getLogger(logger_name)
        lg.handlers = [handler for handler in lg.handlers if not getattr(handler, "_zokyo_handler", False)]
        lg.propagate = False
        if logger_name == "sqlalchemy.engine":
            lg.setLevel(logging.INFO if app.config.get("SQLALCHEMY_ECHO", False) else logging.WARNING)
        else:
            lg.setLevel(log_level)
        lg.addHandler(stderr_handler)
        lg.addFilter(mask_filter)
