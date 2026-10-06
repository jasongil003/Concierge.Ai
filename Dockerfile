FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ARG CONCIERGE_VERSION=unknown
ARG CONCIERGE_COMMIT=unknown
ARG CONCIERGE_BUILD_DATE=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONCIERGE_VERSION=${CONCIERGE_VERSION} \
    CONCIERGE_COMMIT=${CONCIERGE_COMMIT} \
    CONCIERGE_BUILD_DATE=${CONCIERGE_BUILD_DATE}

RUN groupadd --system --gid 10001 concierge && useradd --system --uid 10001 --gid concierge --home-dir /app --shell /usr/sbin/nologin concierge

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tesseract-ocr postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts/migrate_sqlite_to_postgres.py ./scripts/migrate_sqlite_to_postgres.py
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN mkdir -p /state && chown -R concierge:concierge /state

EXPOSE 8080

USER concierge

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
