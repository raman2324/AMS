FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app

RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    pkg-config \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh && \
    addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    mkdir -p /app/media /app/staticfiles && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "ams.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--worker-tmp-dir", "/dev/shm"]
