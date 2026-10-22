FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /app
COPY package.json package-lock.json ./
# --ignore-scripts: no package in the lockfile has an install script, so nothing runs code at install time
RUN npm ci --ignore-scripts
COPY . .
# rewrites are baked at build time: /api/* -> FastAPI
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL NEXT_TELEMETRY_DISABLED=1
# public/ is empty and untracked, so a clean clone has none: create it for the COPY below
RUN mkdir -p public && npm run build

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
LABEL org.opencontainers.image.title="sabzbank-frontend" \
      org.opencontainers.image.source="https://github.com/donmemedo/Charkheh-PakShahr"
# the runtime needs only `node`: drop npm, npx, corepack and yarn, whose bundled deps carry their own CVEs
# (trivy, 2026-10-22: 11 HIGH, all under /usr/local/lib/node_modules/npm in this base image)
RUN rm -rf /usr/local/lib/node_modules /opt/yarn-* \
 && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
# the image's `node` user, numeric so a runtime can verify it is not root
USER 1000:1000
EXPOSE 3000
CMD ["node", "server.js"]
