# Static playground. The auditor itself runs client-side under Pyodide, so this
# image only has to serve files.
FROM nginx:1.27-alpine

COPY index.html app.js samples.js auditor-src.js style.css /usr/share/nginx/html/

RUN printf '%s\n' \
    'server {' \
    '  listen 80;' \
    '  root /usr/share/nginx/html;' \
    '  index index.html;' \
    '  gzip on;' \
    '  gzip_types text/css application/javascript text/html;' \
    '  # Pyodide is fetched from a CDN, so no wasm needs serving here.' \
    '  location / { try_files $uri $uri/ /index.html; }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
