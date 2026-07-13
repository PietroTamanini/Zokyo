from app import create_app
from app.extensions import db
from app.models import OperationalHeartbeat, Organization
from app.utils.operational_metrics import collect_operational_metrics


def test_coleta_metricas_de_runtime_fila_banco_e_heartbeat():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(OperationalHeartbeat(job_name="scheduler", consecutive_failures=0))
        db.session.commit()
        collect_operational_metrics()
