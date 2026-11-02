"""Portal publico de acompanhamento de OS por tenant (Etapa 08).

Rota publica: /consulta-os — renderiza formulário que consome a API segura
já existente em /api/public/os-consulta (sem duplicar logica de consulta).
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from app.services.tenant_site_service import get_public_site_by_host, get_site_content

public_tracking_bp = Blueprint("public_tracking", __name__)


@public_tracking_bp.route("/consulta-os", methods=["GET"])
def index():
    """Renderiza o portal publico de consulta de OS do tenant do dominio."""
    host = request.host
    organization, site = get_public_site_by_host(host)
    if not organization:
        abort(404)
    if not site:
        abort(404, description="Site publico nao esta habilitado para esta empresa.")

    content = get_site_content(organization, site)
    return render_template(
        "pages/public_tracking.html",
        organization=organization,
        site=site,
        content=content,
    )
