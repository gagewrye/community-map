# Single container: FastAPI AppView + static frontend. Fits free tiers (Fly.io, Render, Railway).
FROM python:3.11-slim
WORKDIR /srv
COPY backend backend
COPY frontend frontend
COPY lexicons lexicons
RUN pip install --no-cache-dir ./backend
WORKDIR /srv/backend
ENV CM_DB_PATH=/data/communitymap.db CM_FRONTEND_DIR=/srv/frontend CM_JETSTREAM_ENABLED=true CM_DEV_MODE=false
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
