"""Smoke test transacional da numeracao de laudos em banco com row locking."""
import os
from concurrent.futures import ThreadPoolExecutor

from app import create_app
from app.extensions import db
from app.models.laudo import LaudoCounter
from app.services.laudos import gerar_numero_laudo

TEST_YEAR = int(os.environ.get("LAUDO_CONCURRENCY_TEST_YEAR", "2099"))
WORKERS = int(os.environ.get("LAUDO_CONCURRENCY_WORKERS", "8"))
RESERVATIONS = int(os.environ.get("LAUDO_CONCURRENCY_RESERVATIONS", "24"))


def main():
    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        LaudoCounter.query.filter_by(organization_id=1, ano=TEST_YEAR).delete()
        db.session.commit()

    def reserve(_index):
        with app.app_context():
            number, _year = gerar_numero_laudo(1, TEST_YEAR)
            db.session.commit()
            return number

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            numbers = list(pool.map(reserve, range(RESERVATIONS)))
        expected = {f"LAU-{TEST_YEAR}-{index:06d}" for index in range(1, RESERVATIONS + 1)}
        if set(numbers) != expected:
            raise SystemExit(f"numeracao concorrente inconsistente: {sorted(numbers)}")
        print(f"concurrency ok: {len(numbers)} numeros unicos")
    finally:
        with app.app_context():
            LaudoCounter.query.filter_by(organization_id=1, ano=TEST_YEAR).delete()
            db.session.commit()


if __name__ == "__main__":
    main()
