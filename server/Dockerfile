FROM node:22-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY src ./src
COPY public ./public
RUN mkdir /data && chown node:node /data
ENV STILLFRAME_HOST=0.0.0.0 STILLFRAME_PORT=8484 STILLFRAME_DATA_DIR=/data
USER node
EXPOSE 8484
HEALTHCHECK --interval=30s --timeout=5s CMD node -e "fetch('http://127.0.0.1:8484/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/main.mjs"]
