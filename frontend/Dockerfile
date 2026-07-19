# NexusAgent AI - Frontend production image
# Multi-stage Next.js build, served with `next start` as a non-root user.

# ---- Stage 1: dependencies + build ----
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies based on lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build. NEXT_PUBLIC_* are inlined into the client bundle at
# build time, so the runtime API base URL must be provided here.
COPY . .
# Ensure a public/ dir exists so the runtime COPY is deterministic even if the
# project has no static assets yet.
RUN mkdir -p public
# Compile Next.js telemetry / build (no upload). Fails fast on type errors.
RUN npm run build

# ---- Stage 2: runtime ----
FROM node:20-alpine AS runner

# Build metadata. Injected at build time via --build-arg (e.g. from CI). The
# frontend does not currently expose /version, but recording the SHA/timestamp
# here keeps the images self-describing for provenance/audit.
ARG BUILD_GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ENV BUILD_GIT_SHA=${BUILD_GIT_SHA} \
    BUILD_TIMESTAMP=${BUILD_TIMESTAMP}

ENV NODE_ENV=production \
    PORT=3000

# Create a non-root user.
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 --ingroup nodejs nextjs

WORKDIR /app

# Runtime pieces needed by `next start`.
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next-env.d.ts ./next-env.d.ts

RUN chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD node -e "fetch('http://localhost:3000'+'/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"

# `exec` makes `node` (the `next start` server) PID 1 so it receives SIGTERM
# and shuts down cleanly when the container is stopped. The container runs as
# the non-root `nextjs` user (uid 1001); in production compose it runs with a
# read-only root filesystem + tmpfs `/tmp` (see docker-compose*.yml).
CMD ["sh", "-c", "exec npm run start -- -p ${PORT}"]
