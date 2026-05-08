# Custom Postgres image combining pgvector and Apache AGE.
# Used in production (Railway custom image) and optionally in dev once AGE is needed.
#
# Build & test locally:
#   docker build -t nexus-postgres infra/postgres
#   docker run --rm -e POSTGRES_PASSWORD=nexus nexus-postgres
#
# Block B (knowledge graph wiring) is the first time this image is required.
# Until then, docker-compose uses pgvector/pgvector:pg16 directly.

FROM pgvector/pgvector:pg16

ENV AGE_VERSION=PG16/v1.5.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch ${AGE_VERSION} https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make install \
    && rm -rf /tmp/age

# AGE requires a shared_preload_libraries setting. The init script below applies it.
COPY enable-age.sh /docker-entrypoint-initdb.d/00-enable-age.sh
