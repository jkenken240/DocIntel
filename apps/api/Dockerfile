FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements-dev.lock ./
RUN python -m pip install --require-hashes --no-deps -r requirements-dev.lock

COPY pyproject.toml ./
COPY src ./src
RUN python -m build --wheel --no-isolation --outdir /build/dist


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --require-hashes -r requirements.lock

COPY --from=builder /build/dist/*.whl /tmp/
RUN python -m pip install --no-deps /tmp/*.whl \
    && rm -f /tmp/*.whl

COPY alembic.ini ./
COPY alembic ./alembic

RUN groupadd --system --gid 10001 docintel \
    && useradd --system --uid 10001 --gid docintel --home-dir /app docintel \
    && mkdir -p /data/uploads /data/processed /data/samples /data/backups \
    && chown -R docintel:docintel /app /data

USER docintel

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready', timeout=3)"]

CMD ["uvicorn", "docintel.main:app", "--host", "0.0.0.0", "--port", "8000"]
