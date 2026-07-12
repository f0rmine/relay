FROM python:3.12-slim AS builder

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv "$VIRTUAL_ENV" \
    && /opt/venv/bin/python -m pip install --no-cache-dir --upgrade "pip>=26.1.2"

WORKDIR /build
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --no-deps .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system relay \
    && useradd --system --gid relay --home-dir /app relay

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=relay:relay alembic ./alembic
COPY --chown=relay:relay alembic.ini .
COPY --chown=relay:relay docker-entrypoint.sh /usr/local/bin/relay-entrypoint
RUN chmod 0755 /usr/local/bin/relay-entrypoint \
    && mkdir -p /app/uploads \
    && chown relay:relay /app/uploads

EXPOSE 8000
ENTRYPOINT ["relay-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "1048576"]
