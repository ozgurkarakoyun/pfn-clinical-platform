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

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/models_files /app/static/uploads && \
    chmod +x /app/start.sh

EXPOSE 8080

# Shell form: ${PORT:-8080} expansion deploy ortaminda dogru calissin.
CMD ["sh", "-c", "exec /app/start.sh"]
