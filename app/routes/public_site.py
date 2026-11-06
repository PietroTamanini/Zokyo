"""Blueprint de renderizacao de sites publicos por tenant.

Rotas publicas, sem autenticacao, resolvidas pelo hostname da requisicao.
"""
from __future__ import annotations

from flask import Blueprint, abort, g, make_response, redirect, request, url_for

from app.services.tenant_site_service import get_public_site_by_host
from app.services.tenant_site_bundle import send_bundle_file

public_site_bp = Blueprint("public_site", __name__)


@public_site_bp.route("/", methods=["GET"])
def index():
    """Entrega o index.html publicado pela empresa resolvida pelo host."""
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

    response = send_bundle_file(site, "index.html")
    if response is None:
        abort(404, description="Esta empresa ainda nao publicou os arquivos do site.")
    return response


@public_site_bp.route("/<path:asset_path>", methods=["GET"])
def uploaded_asset(asset_path):
    """Entrega assets e rotas SPA do bundle estatico do tenant."""
    organization, site = get_public_site_by_host(request.host)
    if not organization or not site or site.site_mode != "upload":
        abort(404)
    response = send_bundle_file(site, asset_path)
    if response is None:
        abort(404)
    return response


@public_site_bp.route("/sitemap.xml", methods=["GET"])
def sitemap():
    """Sitemap XML individual por tenant (landing page publica)."""
    organization, site = get_public_site_by_host(request.host)
    if not organization:
        abort(404)
    if not site or site.site_mode != "upload" or not site.site_bundle_version:
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
    if not organization or not site or site.site_mode != "upload" or not site.site_bundle_version:
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
