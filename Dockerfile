# Multi-stage build for Website Intelligence Platform

# Stage 1: Python dependencies
FROM python:3.9-slim as python-builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Node.js dependencies
FROM node:16-slim as node-builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install Node dependencies
RUN npm ci --only=production

# Stage 3: Final image
FROM python:3.9-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    firefox-esr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 wip && \
    mkdir -p /app /data && \
    chown -R wip:wip /app /data

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=python-builder /root/.local /home/wip/.local

# Copy Node dependencies from builder
COPY --from=node-builder /app/node_modules ./node_modules

# Copy application code
COPY --chown=wip:wip . .

# Install Playwright browsers
RUN npx playwright install chromium firefox

# Switch to non-root user
USER wip

# Add Python packages to PATH
ENV PATH=/home/wip/.local/bin:$PATH

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    DATA_PATH=/data

# Create necessary directories
RUN mkdir -p /data/screenshots /data/logs

# Expose ports
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]