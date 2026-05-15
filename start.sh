#!/bin/bash
# Railway PORT environment variable'i icin baslangic scripti
# Bu script shell context'te calistigi icin $PORT dogru expand olur

# PORT degiskeni yoksa 8080 fallback
PORT="${PORT:-8080}"

echo "Starting gunicorn on port: $PORT"
exec gunicorn app:app \
    --bind "0.0.0.0:$PORT" \
    --timeout 300 \
    --workers 1 \
    --preload \
    --max-requests 100
