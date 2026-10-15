# ponytail: pin by digest on the build host once verified: docker manifest inspect python:3.12-slim
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
 && useradd -r -u 10001 -s /usr/sbin/nologin sabz \
 && mkdir -p /data && chown sabz /data
COPY main.py .
ENV DB_PATH=/data/sabz.db PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Tehran
USER sabz
EXPOSE 8000
# --no-proxy-headers: only TRUST_PROXY (main.py) decides whether X-Forwarded-For counts; uvicorn's default trusts
# it from 127.0.0.1. --no-access-log: the Observe middleware already logs each request once, with its request id.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-proxy-headers", "--no-access-log"]
