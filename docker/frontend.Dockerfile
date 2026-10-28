ARG NODE_VERSION=24-slim@sha256:b31e7a42fdf8b8aa5f5ed477c72d694301273f1069c5a2f71d53c6482e99a2fc

FROM node:${NODE_VERSION} AS deps
WORKDIR /repo
RUN corepack enable

# pnpm workspace files live at the repo root.
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./

# Frontend workspace members.
COPY app ./app
COPY frontend-modules ./frontend-modules

RUN pnpm install --frozen-lockfile

FROM node:${NODE_VERSION} AS builder
WORKDIR /repo
RUN corepack enable

# The frontend modules generate their API client via `uv run ocelescope-backend
# openapi`, so the build stage needs uv + the synced Python backend too.
COPY --from=ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca /usr/local/bin/uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
  UV_COMPILE_BYTECODE=1

COPY --from=deps /repo/node_modules ./node_modules

# Backend sources needed to generate the API client.
COPY .python-version pyproject.toml uv.lock ./
COPY backend-modules ./backend-modules

# Frontend workspace + pnpm files.
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY app ./app
COPY frontend-modules ./frontend-modules

RUN uv sync --frozen --all-packages

ENV EXTERNAL_API_BASE_URL="http://backend:8000"

ARG NEXT_PUBLIC_APP_VERSION=0.0.0
ENV NEXT_PUBLIC_APP_VERSION=${NEXT_PUBLIC_APP_VERSION}

# Generate the API client + build the workspace modules, then build the app.
RUN pnpm install --frozen-lockfile \
  && pnpm run build:modules \
  && pnpm --filter @instance/app build

FROM node:${NODE_VERSION} AS runner
WORKDIR /repo

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV EXTERNAL_API_BASE_URL="http://backend:8000"

# The published @ocelescope/* packages stay external and resolve their full ESM
# dependency trees at runtime, which Next's `output: "standalone"` tracing can't
# reliably reproduce in a pnpm workspace. So ship the built workspace with its
# node_modules intact and serve via `next start`. This drops the Python/uv build
# toolchain from the runtime image while keeping module resolution correct.
COPY --from=builder /repo/package.json /repo/pnpm-workspace.yaml /repo/pnpm-lock.yaml ./
COPY --from=builder /repo/node_modules ./node_modules
COPY --from=builder /repo/frontend-modules ./frontend-modules
COPY --from=builder /repo/app ./app

# `next start` writes to app/.next/cache at runtime; give the node user ownership.
RUN chown -R node:node /repo/app/.next

# Run Next's local binary directly so the runtime needs neither pnpm nor
# corepack (which would otherwise download pnpm on first launch).
WORKDIR /repo/app
USER node
EXPOSE 3000

CMD ["node_modules/.bin/next", "start"]
