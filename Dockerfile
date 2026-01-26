# Playwright Screenshot Docker Image
# Based on Ubuntu 24.04
# REST API Service with local Chrome browser

FROM ubuntu:24.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Update and install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    unzip \
    # Playwright/Chrome browser dependencies
    libasound2t64 \
    libatk-bridge2.0-0t64 \
    libatk1.0-0t64 \
    libatspi2.0-0t64 \
    libcairo2 \
    libcups2t64 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0t64 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xvfb \
    # Fonts for proper rendering
    fonts-noto-color-emoji \
    fonts-unifont \
    libfontconfig1 \
    libfreetype6 \
    xfonts-cyrillic \
    xfonts-scalable \
    fonts-liberation \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-tlwg-loma-otf \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

# Copy and install local Chrome browser
COPY chrome-linux64.zip /tmp/chrome-linux64.zip
RUN mkdir -p /opt/chrome \
    && unzip /tmp/chrome-linux64.zip -d /opt/chrome \
    && rm /tmp/chrome-linux64.zip \
    && chmod +x /opt/chrome/chrome-linux64/chrome

# Set Chrome executable path environment variable
ENV CHROME_PATH=/opt/chrome/chrome-linux64/chrome

# Copy application code
COPY screenshot.py .
COPY api.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create output directory
RUN mkdir -p /app/screenshots
ENV SCREENSHOTS_DIR=/app/screenshots

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Default: Run API server with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "api:app"]
