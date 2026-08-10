FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 10001 domovoy \
    && adduser --system --uid 10001 --ingroup domovoy --home /app domovoy

COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --requirement requirements.lock

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/domovoy-entrypoint

RUN chmod +x /usr/local/bin/domovoy-entrypoint \
    && mkdir -p /data/files /data/backups \
    && chown -R domovoy:domovoy /app /data

USER domovoy

EXPOSE 8000
ENTRYPOINT ["domovoy-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
