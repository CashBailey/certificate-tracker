# ==============================================================================
# React Frontend - Production Multi-Stage Build
# ==============================================================================

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY CoreInstances/FrontendWebServer/package.json CoreInstances/FrontendWebServer/package-lock.json* ./
RUN npm ci

COPY CoreInstances/FrontendWebServer/ .

ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# Stage 2: Nginx Runtime
FROM nginx:alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
