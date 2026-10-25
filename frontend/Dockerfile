FROM node:20-alpine

WORKDIR /app

# Install dependencies using lockfile if present
COPY package.json package-lock.json* .
RUN npm ci --silent

# Copy source code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Run Vite dev server listening on all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
