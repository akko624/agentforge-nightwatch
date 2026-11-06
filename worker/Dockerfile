FROM python:3.12.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY requirements.lock ./
COPY backend ./backend
COPY worker ./worker
COPY rules ./rules
COPY schemas ./schemas
COPY alembic.ini ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && \
    pip install --no-cache-dir --no-deps . && \
    groupadd --gid 10001 sqsp && \
    useradd --uid 10001 --gid 10001 --no-create-home sqsp && \
    mkdir -p /data/artifacts && chown -R 10001:10001 /data/artifacts
USER 10001:10001
CMD ["python", "-m", "worker.worker_main"]
