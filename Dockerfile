FROM node:20-slim

ENV NODE_ENV=production

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY server.js index.html viewer.html ./

EXPOSE 30003

CMD ["node", "server.js"]
