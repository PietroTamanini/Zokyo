"""Blueprint de renderizacao de sites publicos por tenant.

Rotas publicas, sem autenticacao, resolvidas pelo hostname da requisicao.
"""
from __future__ import annotations

from flask import Blueprint, abort, current_app, g, make_response, redirect, render_template, request, url_for

from app.services.tenant_site_service import get_public_site_by_host, get_site_content

public_site_bp = Blueprint("public_site", __name__)


@public_site_bp.route("/", methods=["GET"])
def index():
    """Renderiza o site publico institucional da empresa resolvida pelo host."""
    host = request.host
    organization, site = get_public_site_by_host(host)
    if not organization:
        user = getattr(g, "current_user", None)
        if getattr(user, "is_platform_admin", False):
            return redirect(url_for("platform.index"))
        if user is not None:
            from app.routes.pages import dashboard
            return dashboard()
        return redirect(url_for("auth.login_page"))
    if not site:
        abort(404, description="Site publico nao esta habilitado para esta empresa.")

    content = get_site_content(organization, site)
    noindex = bool(current_app.config.get("SEO_BLOCK_TEST_ENVIRONMENTS")) or bool(current_app.testing)
    return render_template(
        "pages/public_site.html",
        organization=organization,
        site=site,
        content=content,
        noindex=noindex,
    )


@public_site_bp.route("/sitemap.xml", methods=["GET"])
def sitemap():
    """Sitemap XML individual por tenant (landing page publica)."""
    organization, site = get_public_site_by_host(request.host)
    if not organization:
        abort(404)
    if not site:
        abort(404, description="Site publico nao esta habilitado para esta empresa.")

    url = f"{request.scheme}://{request.host}/"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url>\n    <loc>{url}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n"
        "</urlset>\n"
    )
    response = make_response(xml)
    response.mimetype = "application/xml"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@public_site_bp.route("/robots.txt", methods=["GET"])
def robots():
    """Robots publico por tenant: libera landing, bloqueia privado/API/painel."""
    organization, site = get_public_site_by_host(request.host)
    if not organization:
        abort(404)
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /consulta-os\n"
        "Disallow: /api/\n"
        "Disallow: /configuracoes/\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
    )
    response = make_response(body)
    response.mimetype = "text/plain; charset=utf-8"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response
