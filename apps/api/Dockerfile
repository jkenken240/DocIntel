FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY src ./src
RUN python -m pip install --no-cache-dir ".[dev]"

COPY alembic ./alembic
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "docintel.main:app", "--host", "0.0.0.0", "--port", "8000"]
