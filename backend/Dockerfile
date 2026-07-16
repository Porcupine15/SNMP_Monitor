FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для easysnmp
RUN apt-get update && apt-get install -y \
    gcc \
    libsnmp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
