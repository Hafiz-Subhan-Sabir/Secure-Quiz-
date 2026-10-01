# IntelliQuiz — Railway (API + Admin Web in one service)
# Build context: repository root

FROM node:20-alpine AS admin-build
WORKDIR /admin
COPY admin-web/package.json admin-web/package-lock.json ./
RUN npm ci
COPY admin-web/ ./
# Same-origin API when admin is served by FastAPI
ENV VITE_API_BASE=/api/v1
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app
RUN pip install --no-cache-dir -e . "psycopg[binary]>=3.2.0"

COPY --from=admin-build /admin/dist ./admin_dist

ENV IQ_DEBUG=false \
    IQ_ADMIN_STATIC_DIR=/app/admin_dist \
    IQ_CORS_ORIGINS=* \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
