# Single-service deployment: FastAPI serves the API, trained models and the built 3D UI.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-deploy.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements-deploy.txt
COPY backend/ ./backend/
COPY models/ ./models/
COPY --from=ui /ui/dist ./frontend/dist
WORKDIR /app/backend
ENV DATABASE_URL=sqlite:////app/backend/dhanrakshak.db ENVIRONMENT=production
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
