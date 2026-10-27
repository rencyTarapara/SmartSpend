FROM node:26-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_BUDGET_API_URL=http://localhost:8001
ARG VITE_ANALYTICS_API_URL=http://localhost:8002
ARG VITE_ALERT_API_URL=http://localhost:8003
ARG VITE_SAVINGS_API_URL=http://localhost:8004
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_BUDGET_API_URL=$VITE_BUDGET_API_URL \
    VITE_ANALYTICS_API_URL=$VITE_ANALYTICS_API_URL \
    VITE_ALERT_API_URL=$VITE_ALERT_API_URL \
    VITE_SAVINGS_API_URL=$VITE_SAVINGS_API_URL

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
