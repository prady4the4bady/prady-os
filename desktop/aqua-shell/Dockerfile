# ────────────────────────────────────────────────────────────────────
# Stage 1 – JS/TS frontend bundle
# ────────────────────────────────────────────────────────────────────
FROM node:20-bookworm-slim AS frontend-build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

COPY index.html tsconfig.json vite.config.ts ./
COPY src/ ./src/
RUN npm run build          # emits static files to /app/dist


# ────────────────────────────────────────────────────────────────────
# Stage 2 – Rust / Tauri binary
# ────────────────────────────────────────────────────────────────────
FROM rust:1.78-bookworm AS rust-build

# Tauri's webkit2gtk / GTK system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
      libwebkit2gtk-4.1-dev \
      libgtk-3-dev \
      libayatana-appindicator3-dev \
      librsvg2-dev \
      libssl-dev \
      pkg-config \
      patchelf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Cargo manifests first so dependency layer is cached
COPY src-tauri/Cargo.toml src-tauri/Cargo.lock* ./src-tauri/
# Stub src so cargo fetch works before copying real source
RUN mkdir -p src-tauri/src && \
    echo 'fn main(){}' > src-tauri/src/main.rs && \
    echo '' > src-tauri/src/lib.rs

WORKDIR /app/src-tauri
RUN cargo fetch

# Now copy real source + the pre-built frontend dist
WORKDIR /app
COPY src-tauri/ ./src-tauri/
COPY --from=frontend-build /app/dist ./dist/

WORKDIR /app/src-tauri
# Build in release mode; Tauri will embed the dist from ../dist via frontendDist
RUN cargo build --release 2>&1


# ────────────────────────────────────────────────────────────────────
# Stage 3 – Minimal runtime image
# ────────────────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS runtime

# Runtime shared libraries required by webkit2gtk and GTK
RUN apt-get update && apt-get install -y --no-install-recommends \
      libwebkit2gtk-4.1-0 \
      libgtk-3-0 \
      libayatana-appindicator3-1 \
      librsvg2-2 \
      libssl3 \
      ca-certificates \
      # X11 client libs for DISPLAY passthrough
      libx11-6 \
      libxext6 \
      libxrender1 \
      # Wayland
      libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/aqua-shell

COPY --from=rust-build /app/src-tauri/target/release/aqua-shell .

RUN useradd -m -u 1000 app && \
  chown -R app:app /opt/aqua-shell

USER app

# Notification server port
EXPOSE 11435

ENV MODEL_GATEWAY_URL=http://model-gateway:11430
ENV WORKFLOW_ENGINE_URL=http://workflow-engine:8001

CMD ["./aqua-shell"]
