FROM python:3.11.7-slim

# Sistem paketleri (OpenCV/Ultralytics icin)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libxml2 \
    libjpeg62-turbo \
    libpng16-16 \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python paketleri
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Uygulama
COPY . .

# Gereken klasorler + start.sh executable
RUN mkdir -p /app/models_files /app/static/uploads && \
    chmod +x /app/start.sh

# Port (Railway $PORT environment variable kullanir)
EXPOSE 8080

# Start.sh ile bash uzerinden calistir - $PORT dogru expand olur
ENTRYPOINT ["/bin/bash", "/app/start.sh"]
