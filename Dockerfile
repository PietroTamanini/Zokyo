FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements-prod.txt

COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin zokyo \
    && mkdir -p /app/instance/uploads/reports /var/log/zokyo /var/run/zokyo \
    && chown -R zokyo:zokyo /app /var/log/zokyo /var/run/zokyo

USER zokyo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
