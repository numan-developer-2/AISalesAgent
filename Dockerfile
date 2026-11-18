FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY src ./src
COPY public ./public
COPY index.html tsconfig.json vite.config.ts ./
RUN npm run build:connected

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONPATH=/app/backend/src PYTHONUNBUFFERED=1
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/src backend/src
COPY config/businesses config/businesses
COPY data/knowledge data/knowledge
COPY public public
COPY scripts/setup_workspace.py scripts/setup_workspace.py
COPY --from=frontend /build/dist dist
RUN useradd -m app && mkdir -p data/runtime && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "workspace.api:app", "--host", "0.0.0.0", "--port", "8000"]
