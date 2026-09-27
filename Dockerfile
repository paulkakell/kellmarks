# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KELLMARKS_DATA_FILE=/data/data.json \
    KELLMARKS_REQUIRE_AUTH=1 \
    HOME=/tmp

WORKDIR /app
COPY docs/server/requirements.lock /app/docs/server/requirements.lock
COPY docker/requirements.txt /app/docker/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/docker/requirements.txt \
    && python -m pip check \
    && groupadd --gid 10001 kellmarks \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin kellmarks \
    && mkdir /data \
    && chown 10001:10001 /data \
    && chmod 700 /data

# Explicit copies and the build-context allowlist exclude secrets and private data.
COPY docs/server/*.py /app/docs/server/
COPY docs/index.html docs/favicon.ico /app/docs/
COPY docs/assets/app.js docs/assets/app.css docs/assets/enhancements.js \
     docs/assets/logo.svg docs/assets/sample-data.json docs/assets/site-tags.json /app/docs/assets/
COPY docker/gunicorn.conf.py docker/healthcheck.py /app/docker/
COPY VERSION LICENSE /app/

USER 10001:10001
WORKDIR /app/docs/server
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]
CMD ["gunicorn", "--config", "/app/docker/gunicorn.conf.py", "app:app"]
