# X-Ray web — Vite build served by nginx, /api proxied same-origin to the API.
# Build from the repo root:  docker build -f apps/web/Dockerfile -t xray-web .
FROM node:22-alpine AS build
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --no-audit --no-fund
COPY apps/web apps/web
# Same-origin API: requests go to /api/... and nginx forwards them.
ENV VITE_XRAY_API_BASE_URL=""
RUN npm run build --workspace @xray/web

FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
ENV API_UPSTREAM=http://api:8000 PORT=8080
EXPOSE 8080
