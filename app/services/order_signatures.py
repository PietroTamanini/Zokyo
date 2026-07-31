"""Captura privada e verificável de assinatura em ordens de serviço."""
import hashlib
import io
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError

from app.extensions import db
from app.models import OrderSignature


def signature_root():
    configured = current_app.config.get("SIGNATURE_UPLOAD_FOLDER")
    root = Path(configured) if configured else Path(current_app.instance_path) / "uploads" / "signatures"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def capture_signature(order, user_id, signer_name, uploaded_file, ip_address):
    signer_name = (signer_name or "").strip()
    if len(signer_name) < 2:
        raise ValueError("Nome do signatario e obrigatorio.")
    raw = uploaded_file.read(1_000_001)
    if not raw or len(raw) > 1_000_000:
        raise ValueError("Assinatura deve ter no maximo 1 MB.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Imagem de assinatura invalida.") from exc
    width, height = image.size
    if width < 200 or height < 80 or width > 2000 or height > 1000:
        raise ValueError("Dimensoes da assinatura sao invalidas.")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    content = output.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    relative = Path(str(order.organization_id)) / f"{secrets.token_hex(20)}.png"
    target = (signature_root() / relative).resolve()
    if not target.is_relative_to(signature_root()):
        raise ValueError("Destino de assinatura inválido.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(content)
    temporary.replace(target)
    now = datetime.now(timezone.utc)
    for existing in OrderSignature.query.filter_by(order_id=order.id, revoked_at=None).all():
        existing.revoked_at = now
    signature = OrderSignature(
        organization_id=order.organization_id, order_id=order.id, captured_by_id=user_id,
        signer_name=signer_name[:120], storage_key=relative.as_posix(), size_bytes=len(content),
        sha256=digest, ip_address=(ip_address or "")[:45] or None,
    )
    db.session.add(signature)
    return signature


def signature_path(signature):
    path = (signature_root() / signature.storage_key).resolve()
    if not path.is_relative_to(signature_root()) or not path.is_file():
        raise FileNotFoundError("Assinatura não encontrada.")
    return path
