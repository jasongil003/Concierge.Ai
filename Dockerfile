FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ARG CONCIERGE_VERSION=unknown
ARG CONCIERGE_COMMIT=unknown
ARG CONCIERGE_BUILD_DATE=unknown
ARG POSTGRES_CLIENT_MAJOR=16

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONCIERGE_VERSION=${CONCIERGE_VERSION} \
    CONCIERGE_COMMIT=${CONCIERGE_COMMIT} \
    CONCIERGE_BUILD_DATE=${CONCIERGE_BUILD_DATE}

RUN groupadd --system --gid 10001 concierge && useradd --system --uid 10001 --gid concierge --home-dir /app --shell /usr/sbin/nologin concierge

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends tesseract-ocr curl ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --silent --show-error --location \
       https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && printf 'Types: deb\nURIs: https://apt.postgresql.org/pub/repos/apt\nSuites: %s-pgdg\nComponents: main\nSigned-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/pgdg.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends "postgresql-client-${POSTGRES_CLIENT_MAJOR}" \
    && rm -rf /var/lib/apt/lists/*

# Keep backup tools aligned with the deployed server. Newer pg_restore emits
# settings such as transaction_timeout that an older server cannot execute.
ENV PATH="/usr/lib/postgresql/${POSTGRES_CLIENT_MAJOR}/bin:${PATH}"

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
