"""routes/onboarding.py — Fluxo de onboarding de 10 etapas para novas assistencias."""

from flask import Blueprint, g, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Configuracao
from app.utils.auth import nivel_required

onboarding_bp = Blueprint("onboarding", __name__)

# 10 etapas do onboarding
ONBOARDING_STEPS = [
    "empresa_cadastro",         # 1. Cadastro da empresa
    "dados_comerciais",        # 2. Dados comerciais
    "assistencia_config",      # 3. Configuração da assistência
    "funcionarios_cadastro",   # 4. Cadastro de funcionários
    "servicos_config",         # 5. Configuração de serviços
    "financeira_config",       # 6. Configuração financeira
    "estoque_cadastro",        # 7. Cadastro de estoque
    "site_personalizacao",     # 8. Personalização do site
    "dominio_config",          # 9. Configuração do domínio
    "primeira_os",             # 10. Primeira ordem de serviço
]


def _get_config(organization_id: int = None) -> Configuracao:
    """Retorna a configuração da organização, criando se não existir."""
    org_id = organization_id or getattr(g, "organization_id", None)
    cfg = Configuracao.get(org_id)
    if cfg is None:
        cfg = Configuracao(organization_id=org_id)
        db.session.add(cfg)
        db.session.flush()
    return cfg


def _is_onboarding_complete(org_id: int) -> bool:
    """Verifica se o onboarding foi concluído para esta organização."""
    cfg = _get_config(org_id)
    return bool(cfg.onboarding_completed)


@onboarding_bp.route("/")
@nivel_required("admin", "operacional")
def index():
    """Ponto de entrada do onboarding — mostra a etapa atual."""
    cfg = _get_config()
    step = cfg.onboarding_step
    total_steps = len(ONBOARDING_STEPS)

    # Se já concluído, redireciona para dashboard
    if cfg.onboarding_completed:
        return redirect(url_for("pages.dashboard"))

    # Obter dados atuais da etapa
    step_data = cfg.onboarding_data or {}

    return render_template(
        "pages/onboarding.html",
        active="onboarding",
        step=step,
        total_steps=total_steps,
        step_name=ONBOARDING_STEPS[step - 1] if 1 <= step <= total_steps else "",
        step_data=step_data,
        onboarding_completed=cfg.onboarding_completed,
    )


@onboarding_bp.route(
    "/<any(empresa_cadastro,dados_comerciais,assistencia_config,funcionarios_cadastro,"
    "servicos_config,financeira_config,estoque_cadastro,site_personalizacao,"
    "dominio_config,primeira_os):step_name>",
    methods=["GET", "POST"],
)
@nivel_required("admin", "operacional")
def step(step_name):
    """Rota genérica para cada etapa do onboarding."""
    cfg = _get_config()
    total_steps = len(ONBOARDING_STEPS)

    # Se já concluído, redireciona para dashboard
    if cfg.onboarding_completed:
        return redirect(url_for("pages.dashboard"))

    # Validar que esta é uma etapa válida
    if step_name not in ONBOARDING_STEPS:
        return redirect(url_for(".index"))

    # Se nao for POST e estiver na etapa errada, redireciona
    if request.method == "GET" and cfg.onboarding_step != ONBOARDING_STEPS.index(step_name) + 1:
        return redirect(url_for(".step", step_name=ONBOARDING_STEPS[cfg.onboarding_step - 1]))

    # Processar submissão
    if request.method == "POST":
        step_data = cfg.onboarding_data or {}
        # Salvar dados da etapa atual
        step_data[step_name] = request.form.to_dict()

        # Verificar se há campos de "concluir" nesta etapa
        # Cada etapa pode ter campos que indicam avanço automático

        # Atualizar configuração
        cfg.onboarding_data = step_data
        # Avançar para próxima etapa, a menos que esta seja a última
        if step_name == ONBOARDING_STEPS[-1]:  # Última etapa
            cfg.onboarding_completed = True
        else:
            cfg.onboarding_step = ONBOARDING_STEPS.index(step_name) + 2

        db.session.add(cfg)
        db.session.commit()

        # Se foi a última etapa, redirecionar para dashboard
        if cfg.onboarding_completed:
            return redirect(url_for("pages.dashboard"))
        else:
            # Próxima etapa
            next_step = ONBOARDING_STEPS.index(step_name) + 2
            return redirect(url_for(".step", step_name=ONBOARDING_STEPS[next_step - 1]))

    # GET - renderizar a etapa
    # Dados atuais da etapa
    current_data = cfg.onboarding_data.get(step_name, {}) if cfg.onboarding_data else {}

    return render_template(
        "pages/onboarding_step.html",
        active="onboarding",
        step=cfg.onboarding_step,
        total_steps=total_steps,
        step_name=step_name,
        step_names=ONBOARDING_STEPS,
        current_step_data=current_data,
        is_first=(cfg.onboarding_step == 1),
        is_last=(cfg.onboarding_step == total_steps),
    )


@onboarding_bp.route("/pular/<step_name>", methods=["POST"])
@nivel_required("admin", "operacional")
def pular(step_name):
    """Permite pular uma etapa (opcional)."""
    cfg = _get_config()

    # Se for a última etapa antes da conclusao, marcar como concluido pular
    if cfg.onboarding_step < len(ONBOARDING_STEPS):
        cfg.onboarding_step = ONBOARDING_STEPS.index(step_name) + 2
    else:
        cfg.onboarding_completed = True

    db.session.add(cfg)
    db.session.commit()

    if cfg.onboarding_completed:
        return redirect(url_for("pages.dashboard"))
    else:
        return redirect(url_for(".step", step_name=ONBOARDING_STEPS[cfg.onboarding_step - 1]))


@onboarding_bp.route("/concluir", methods=["POST"])
@nivel_required("admin", "operacional")
def concluir():
    """Marca o onboarding como concluído manualmente."""
    cfg = _get_config()
    cfg.onboarding_completed = True
    cfg.onboarding_step = len(ONBOARDING_STEPS) + 1
    db.session.add(cfg)
    db.session.commit()
    return redirect(url_for("pages.dashboard"))


@onboarding_bp.route("/reset", methods=["POST"])
@nivel_required("admin", "operacional")
def reset():
    """Reseta o onboarding para recomeçar."""
    cfg = _get_config()
    cfg.onboarding_step = 1
    cfg.onboarding_completed = False
    cfg.onboarding_data = {}
    db.session.add(cfg)
    db.session.commit()
    return redirect(url_for(".index"))