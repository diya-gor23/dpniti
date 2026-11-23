FROM node:20-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx python3 python3-venv supervisor build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app/backend
COPY backend/package.json backend/package-lock.json ./
RUN npm ci --omit=dev
COPY backend/ ./

WORKDIR /app/chatbot
COPY chatbot/requirements.txt ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY chatbot/ ./

COPY frontend/ /app/frontend/
COPY deploy/render/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/render/supervisord.conf /etc/supervisor/conf.d/dpniti.conf

EXPOSE 10000
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/dpniti.conf"]
