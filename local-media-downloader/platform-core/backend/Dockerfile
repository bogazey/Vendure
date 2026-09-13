FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libpq5 tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10101 platform \
    && useradd --uid 10101 --gid platform --create-home platform

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/platform-core-entrypoint
RUN chmod 0755 /usr/local/bin/platform-core-entrypoint \
    && mkdir -p /var/lib/platform-core/data \
    && chown -R platform:platform /app /var/lib/platform-core

USER platform
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/platform-core-entrypoint"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
