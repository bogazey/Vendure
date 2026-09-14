FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Empty (not unset) means same-origin: the production reverse proxy routes
# /api/*, /oauth/*, /.well-known/* on this same host to the backend - see
# platform-core/reverse-proxy/nginx.production.conf and
# account-frontend/src/services/api.ts for why this must stay `??`, never
# `||`, downstream.
ARG VITE_PLATFORM_API_BASE_URL=
ENV VITE_PLATFORM_API_BASE_URL=${VITE_PLATFORM_API_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
