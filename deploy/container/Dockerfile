# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:22-bookworm-slim
ARG GO_IMAGE=golang:1.25-bookworm
ARG RUNTIME_IMAGE=ubuntu:24.04

FROM ${NODE_IMAGE} AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM ${GO_IMAGE} AS backend
WORKDIR /src
COPY go.mod go.sum ./
ARG GOPROXY=https://proxy.golang.org,direct
ARG GOSUMDB=sum.golang.org
RUN GOPROXY="${GOPROXY}" GOSUMDB="${GOSUMDB}" go mod download
COPY cli/ ./cli/
COPY server/ ./server/
ARG VERSION=container-dev
RUN CGO_ENABLED=0 go build -buildvcs=false -trimpath -ldflags "-s -w -X main.version=${VERSION}" -o /out/mindfs ./cli/cmd

FROM ${NODE_IMAGE} AS codex
ARG CODEX_VERSION=0.162.1
RUN npm install --global --no-audit --no-fund @openai/codex@${CODEX_VERSION}

FROM ${RUNTIME_IMAGE} AS runtime
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates git openssh-client bash python3 ripgrep curl procps libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
ARG MINDFS_UID=1000
ARG MINDFS_GID=1000
RUN (getent group "${MINDFS_GID}" >/dev/null || groupadd --gid "${MINDFS_GID}" mindfs) \
    && useradd --non-unique --uid "${MINDFS_UID}" --gid "${MINDFS_GID}" --create-home --shell /bin/bash mindfs \
    && mkdir -p /workspace /opt/rcc/bin \
    && chown "${MINDFS_UID}:${MINDFS_GID}" /workspace
COPY --from=backend /out/mindfs /usr/local/bin/mindfs
COPY --from=web /src/web/dist/ /usr/local/share/mindfs/web/
COPY agents.json task_template.json LICENSE /usr/local/share/mindfs/
COPY deploy/container/entrypoint.sh /usr/local/bin/mindfs-container-entrypoint
RUN chmod 0755 /usr/local/bin/mindfs-container-entrypoint
ENV HOME=/home/mindfs \
    CODEX_HOME=/home/mindfs/.codex \
    XDG_CONFIG_HOME=/home/mindfs/.config \
    XDG_STATE_HOME=/home/mindfs/.local/state \
    PATH=/opt/rcc/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
USER mindfs
WORKDIR /workspace
EXPOSE 7331
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s CMD curl --fail --silent http://127.0.0.1:7331/health >/dev/null || exit 1
ENTRYPOINT ["mindfs-container-entrypoint"]
CMD ["mindfs", "--foreground", "--addr", ":7331", "--no-relayer", "--web-push=false", "--title", "MindFS RCC Container", "/workspace"]
