"""Portal publico minimo para acompanhamento e aprovacao de orcamento."""
from flask import Blueprint, abort, make_response, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import OrdemServico, Usuario
from app.services.portal import buscar_token_portal, criar_link_portal, decidir_orcamento
from app.utils.auth import nivel_required

portal_bp = Blueprint("portal", __name__)


def _public_response(template, **context):
    response = make_response(render_template(template, **context))
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@portal_bp.route("/os/<int:os_id>/portal-link", methods=["POST"])
@nivel_required("admin", "operacional")
def gerar_link(os_id):
    usuario = db.session.get(Usuario, session.get("usuario_id"))
    os_obj = OrdemServico.query.filter_by(id=os_id, organization_id=usuario.organization_id).first_or_404()
    purpose = request.form.get("purpose", "tracking")
    try:
        raw_token = criar_link_portal(os_obj, usuario, purpose, request.form.get("dias", 30, type=int))
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return render_template("pages/portal_link_result.html", erro=str(exc), os=os_obj), 400
    link = url_for("portal.publico", token=raw_token, _external=True)
    return render_template("pages/portal_link_result.html", link=link, purpose=purpose, os=os_obj)


@portal_bp.route("/portal/os/<token>", methods=["GET", "POST"])
def publico(token):
    portal_token = buscar_token_portal(token)
    if not portal_token:
        abort(404)
    if request.method == "POST":
        try:
            decidir_orcamento(portal_token, request.form.get("decisao", ""))
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            response = _public_response("pages/portal_os.html", portal_token=portal_token, os=portal_token.os, erro=str(exc))
            response.status_code = 409
            return response
        return redirect(url_for("portal.publico", token=token))
    return _public_response("pages/portal_os.html", portal_token=portal_token, os=portal_token.os)
