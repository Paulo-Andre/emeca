FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend_publico/package*.json ./
RUN npm ci
COPY frontend_publico/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /frontend/dist /app/frontend_publico/dist

RUN chmod +x /app/entrypoint.sh && \
    DJANGO_DEBUG=1 python manage.py collectstatic --noinput

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
