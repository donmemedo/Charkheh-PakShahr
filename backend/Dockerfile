FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
LABEL org.opencontainers.image.title="sabzbank-backend" \
      org.opencontainers.image.source="https://github.com/donmemedo/Charkheh-PakShahr"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
 && useradd -r -u 10001 -s /usr/sbin/nologin sabz \
 && mkdir -p /data && chown sabz /data
# ops.py: backup and ledger check, run by the compose "ops" and "ledger-check" profiles
COPY main.py ops.py ./
ENV DB_PATH=/data/sabz.db PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Tehran
# numeric (the sabz user above), so a runtime can verify it is not root
USER 10001
EXPOSE 8000
# --no-proxy-headers: only TRUST_PROXY (main.py) decides whether X-Forwarded-For counts; uvicorn's default trusts
# it from 127.0.0.1. --no-access-log: the Observe middleware already logs each request once, with its request id.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-proxy-headers", "--no-access-log"]
