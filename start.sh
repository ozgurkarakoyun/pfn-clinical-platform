#!/usr/bin/env sh
set -eu

# Railway/Render/Heroku PORT degiskenini kullanir.
# Bazi deploy ayarlarinda PORT yanlislikla literal "$PORT" olarak gelebilir;
# bu durumda guvenli fallback 8080 kullanilir.
PORT_VALUE="${PORT:-8080}"

if [ "$PORT_VALUE" = '\$PORT' ] || [ "$PORT_VALUE" = 'PORT' ] || [ -z "$PORT_VALUE" ]; then
    PORT_VALUE="8080"
fi

case "$PORT_VALUE" in
    *[!0-9]*)
        echo "Invalid PORT value: $PORT_VALUE. Falling back to 8080."
        PORT_VALUE="8080"
        ;;
esac

echo "Starting gunicorn on port: $PORT_VALUE"
exec gunicorn app:app \
    --bind "0.0.0.0:${PORT_VALUE}" \
    --timeout 300 \
    --workers 1 \
    --max-requests 100
