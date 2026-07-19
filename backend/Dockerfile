ARG INSTALL_DEV=false

FROM python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba AS builder

ARG INSTALL_DEV

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsnmp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-dev.txt ./requirements-dev.txt
COPY backend/requirements.lock ./requirements.lock
COPY backend/requirements-dev.lock ./requirements-dev.lock
RUN if [ "$INSTALL_DEV" = "true" ]; then requirements_file=requirements-dev.lock; else requirements_file=requirements.lock; fi \
    && pip wheel --no-cache-dir --require-hashes --wheel-dir /wheels -r "$requirements_file"

FROM python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba

ARG INSTALL_DEV

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsnmp40 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system --gid 10001 snmp-monitor \
    && adduser --system --uid 10001 --gid 10001 --no-create-home snmp-monitor

COPY --from=builder /wheels /wheels
COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-dev.txt ./requirements-dev.txt
COPY backend/requirements.lock ./requirements.lock
COPY backend/requirements-dev.lock ./requirements-dev.lock
RUN pip install --no-cache-dir --no-index --no-deps /wheels/*.whl \
    && rm -rf /wheels

COPY --chown=10001:10001 backend/ ./
COPY --chown=10001:10001 frontend/ ./frontend/

USER 10001:10001

# Database migrations are an explicit deployment step. This prevents an
# application restart from changing the production schema unexpectedly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
