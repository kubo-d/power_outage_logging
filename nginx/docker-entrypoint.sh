#!/bin/sh
set -e
# Substitute API_KEY into template
if [ -z "$API_KEY" ]; then
  echo "Warning: API_KEY not set — auth will always fail (401)."
fi
envsubst '$API_KEY' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
exec "$@"
