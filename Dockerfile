# Python base imaji - Debian Slim (kucuk ama OpenCV icin sistem paketleri ekleyecegiz)
FROM python:3.11.7-slim

# Sistem paketleri - OpenCV/Ultralytics icin gerekli
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
    && rm -rf /var/lib/apt/lists/*

# Calisma klasoru
WORKDIR /app

# Once requirements - cache icin
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Kalan dosyalar
COPY . .

# Klasor olustur (yoksa)
RUN mkdir -p /app/models_files /app/static/uploads

# Railway PORT environment variable kullanir
ENV PORT=8080
EXPOSE 8080

# Gunicorn ile baslat (preload onemli - modeller master'da indirilir)
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1 --preload --max-requests 100
