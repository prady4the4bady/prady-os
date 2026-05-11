# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Lumyn sandbox image — Lumyn + Vyrex plugin inside OpenShell
#
# Layers PR-specific code (plugin, config, startup script) on top of the
# pre-built Lumyn base image. Mirrors the OpenClaw Dockerfile structure.

ARG BASE_IMAGE=ghcr.io/nvidia/vyrex/lumyn-sandbox-base:latest

# hadolint ignore=DL3006
FROM ${BASE_IMAGE}

# Keep the final image contract explicit even when the published base image
# changes independently of this Dockerfile.
RUN set -eu; \
    lumyn_path="$(command -v lumyn 2>/dev/null || true)"; \
    if [ "$lumyn_path" != "/usr/local/bin/lumyn" ]; then \
        echo "ERROR: expected lumyn at /usr/local/bin/lumyn, got ${lumyn_path:-missing}" >&2; \
        exit 1; \
    fi; \
    test -x /usr/local/bin/lumyn; \
    /usr/local/bin/lumyn --version

# Harden: remove unnecessary build tools and network probes
RUN (apt-get remove --purge -y gcc gcc-12 g++ g++-12 cpp cpp-12 make \
        netcat-openbsd netcat-traditional ncat 2>/dev/null || true) \
    && apt-get autoremove --purge -y \
    && rm -rf /var/lib/apt/lists/*

# Lumyn v2026.4.13+ auto-detects HTTPS_PROXY and skips fallback-IP
# transport when a proxy is present. The sandbox proxy chain
# (decode-proxy → OpenShell L7 proxy) handles credential placeholder
# rewriting and hostname-based policy enforcement. No monkey patch needed.
ENV LUMYN_TELEGRAM_DISABLE_FALLBACK_IPS=1

# Copy Vyrex plugin for Lumyn (Python-based)
COPY agents/lumyn/plugin/ /opt/vyrex-lumyn-plugin/
RUN chmod -R a+rX /opt/vyrex-lumyn-plugin/

# Copy config generation script and URL-decode proxy
COPY agents/lumyn/generate-config.ts /opt/vyrex-generate-config.ts
RUN chmod 444 /opt/vyrex-generate-config.ts
COPY agents/lumyn/decode-proxy.py /usr/local/bin/vyrex-decode-proxy
RUN chmod 755 /usr/local/bin/vyrex-decode-proxy

# Copy blueprint (shared infrastructure)
COPY vyrex-blueprint/ /opt/vyrex-blueprint/
# Ensure sandbox user can read blueprint files copied as root
RUN chmod -R a+rX /opt/vyrex-blueprint/

# Copy startup script
COPY scripts/lib/sandbox-init.sh /usr/local/lib/vyrex/sandbox-init.sh
COPY agents/lumyn/start.sh /usr/local/bin/vyrex-start
RUN chmod 755 /usr/local/bin/vyrex-start /usr/local/lib/vyrex/sandbox-init.sh

# Build args for config that varies per deployment.
ARG VYREX_MODEL=nvidia/nemotron-3-super-120b-a12b
ARG VYREX_PROVIDER_KEY=custom
ARG VYREX_INFERENCE_BASE_URL=https://inference.local/v1
# CHAT_UI_URL is a legacy name shared with the OpenClaw build arg. For
# Lumyn this URL points at the OpenAI-compatible API server (port 8642,
# exposing /v1 and /health), NOT a browser chat UI. Callers authenticate
# via a bearer token in the Authorization header. See
# agents/lumyn/manifest.yaml (dashboard.kind: api).
ARG CHAT_UI_URL=http://127.0.0.1:8642
ARG VYREX_MESSAGING_CHANNELS_B64=W10=
ARG VYREX_MESSAGING_ALLOWED_IDS_B64=e30=
ARG VYREX_BUILD_ID=default

# Promote build-args to env vars for the config generation script.
ENV VYREX_MODEL=${VYREX_MODEL} \
    VYREX_PROVIDER_KEY=${VYREX_PROVIDER_KEY} \
    VYREX_INFERENCE_BASE_URL=${VYREX_INFERENCE_BASE_URL} \
    CHAT_UI_URL=${CHAT_UI_URL} \
    VYREX_MESSAGING_CHANNELS_B64=${VYREX_MESSAGING_CHANNELS_B64} \
    VYREX_MESSAGING_ALLOWED_IDS_B64=${VYREX_MESSAGING_ALLOWED_IDS_B64}

WORKDIR /sandbox
USER sandbox

# Set up blueprint for local resolution
RUN mkdir -p /sandbox/.vyrex/blueprints/0.1.0 \
    && cp -r /opt/vyrex-blueprint/* /sandbox/.vyrex/blueprints/0.1.0/

# Generate Lumyn config.yaml and .env from build args.
# Config is mutable by default (600 sandbox:sandbox). Immutability is opt-in
# via `shields up`. .env holds API key placeholders for OpenShell provider pipeline.
# SECURITY: Uses a separate script file instead of inline code to avoid
# code injection via build-arg interpolation (same concern as OpenClaw C-2).
RUN node --experimental-strip-types /opt/vyrex-generate-config.ts

# Install Vyrex plugin into Lumyn
RUN mkdir -p /sandbox/.lumyn/plugins/vyrex \
    && cp -r /opt/vyrex-lumyn-plugin/* /sandbox/.lumyn/plugins/vyrex/

# Write a default SOUL.md for the sandboxed agent.
RUN mkdir -p /sandbox/.lumyn/memories \
    && printf '%s\n' \
    'You are a helpful AI assistant running inside an NVIDIA OpenShell sandbox.' \
    'Your inference is routed through Vyrex. You have access to terminal,' \
    'file, and web tools. Be concise and helpful.' \
    > /sandbox/.lumyn/SOUL.md

# Set mutable-default permissions (640/750 sandbox:sandbox).
# The sandbox user can write config; the gateway user can read it via
# supplementary sandbox-group membership. Shields-up applies 444 root:root +
# chattr +i.
# hadolint ignore=DL3002
USER root
# Flatten stale published base images that still contain the old .lumyn-data
# symlink bridge. OpenShell starts the sandbox as the sandbox user, so runtime
# migration cannot rely on root privileges inside the pod.
# hadolint ignore=DL4006
RUN set -eu; \
    config_dir=/sandbox/.lumyn; \
    data_dir=/sandbox/.lumyn-data; \
    mkdir -p "$config_dir"; \
    if [ -L "$data_dir" ]; then \
        echo "ERROR: refusing legacy layout cleanup because $data_dir is a symlink" >&2; \
        exit 1; \
    fi; \
    if [ -d "$data_dir" ]; then \
        for entry in "$data_dir"/*; do \
            [ -e "$entry" ] || [ -L "$entry" ] || continue; \
            if [ -L "$entry" ]; then \
                echo "ERROR: refusing legacy layout cleanup because $entry is a symlink" >&2; \
                exit 1; \
            fi; \
            name="$(basename "$entry")"; \
            target="$config_dir/$name"; \
            if [ -L "$target" ]; then \
                rm -f "$target"; \
            fi; \
            if [ -d "$entry" ]; then \
                mkdir -p "$target"; \
                cp -a "$entry"/. "$target"/; \
            elif [ ! -e "$target" ]; then \
                cp -a "$entry" "$target"; \
            fi; \
        done; \
        data_real="$(readlink -f "$data_dir" 2>/dev/null || printf '%s' "$data_dir")"; \
        while :; do \
            replaced_marker="$(mktemp)"; \
            rm -f "$replaced_marker"; \
            find "$config_dir" -type l -print | while IFS= read -r link; do \
                raw_target="$(readlink "$link" 2>/dev/null || true)"; \
                resolved_target="$(readlink -f "$link" 2>/dev/null || true)"; \
                legacy_target=0; \
                case "$raw_target" in "$data_real"/* | "$data_dir"/*) legacy_target=1 ;; esac; \
                case "$resolved_target" in "$data_real"/* | "$data_dir"/*) legacy_target=1 ;; esac; \
                if [ "$legacy_target" -eq 1 ]; then \
                    copy_target="$resolved_target"; \
                    if [ -z "$copy_target" ] || { [ ! -e "$copy_target" ] && [ ! -L "$copy_target" ]; }; then \
                        copy_target="$raw_target"; \
                    fi; \
                    if [ -d "$copy_target" ] && [ ! -L "$copy_target" ]; then \
                            rm -f "$link"; \
                            mkdir -p "$link"; \
                            cp -a "$copy_target"/. "$link"/; \
                    elif [ -e "$copy_target" ] || [ -L "$copy_target" ]; then \
                            rm -f "$link"; \
                            cp -a "$copy_target" "$link"; \
                    else \
                        echo "ERROR: legacy symlink target missing: $link -> ${raw_target:-$resolved_target}" >&2; \
                        exit 1; \
                    fi; \
                    : > "$replaced_marker"; \
                fi; \
            done; \
            if [ ! -e "$replaced_marker" ]; then \
                rm -f "$replaced_marker"; \
                break; \
            fi; \
            rm -f "$replaced_marker"; \
        done; \
        rm -rf "$data_dir"; \
    fi; \
    mkdir -p "$config_dir/memories" \
        "$config_dir/sessions" \
        "$config_dir/skills" \
        "$config_dir/plugins" \
        "$config_dir/cron" \
        "$config_dir/logs" \
        "$config_dir/skins" \
        "$config_dir/plans" \
        "$config_dir/workspace" \
        "$config_dir/profiles" \
        "$config_dir/cache" \
        "$config_dir/pairing" \
        "$config_dir/runtime"; \
    if [ -e "$data_dir" ] || [ -L "$data_dir" ]; then \
        echo "ERROR: legacy data dir still exists after cleanup: $data_dir" >&2; \
        exit 1; \
    fi; \
    data_real="$(readlink -f "$data_dir" 2>/dev/null || printf '%s' "$data_dir")"; \
    find "$config_dir" -type l -print | while IFS= read -r link; do \
        raw_target="$(readlink "$link" 2>/dev/null || true)"; \
        resolved_target="$(readlink -f "$link" 2>/dev/null || true)"; \
        case "$raw_target" in \
            "$data_real"/* | "$data_dir"/*) \
                echo "ERROR: legacy symlink remains after cleanup: $link -> $raw_target" >&2; \
                exit 1; \
                ;; \
        esac; \
        case "$resolved_target" in \
            "$data_real"/* | "$data_dir"/*) \
                echo "ERROR: legacy symlink remains after cleanup: $link -> $resolved_target" >&2; \
                exit 1; \
                ;; \
        esac; \
    done; \
    rm -rf /root/.cache/pip /sandbox/.cache \
    && chown -R sandbox:sandbox /sandbox/.lumyn \
    && chown gateway:sandbox /sandbox/.lumyn/runtime \
    && chmod 750 /sandbox/.lumyn \
    && chmod 770 \
        /sandbox/.lumyn/memories \
        /sandbox/.lumyn/sessions \
        /sandbox/.lumyn/skills \
        /sandbox/.lumyn/plugins \
        /sandbox/.lumyn/cron \
        /sandbox/.lumyn/logs \
        /sandbox/.lumyn/skins \
        /sandbox/.lumyn/plans \
        /sandbox/.lumyn/workspace \
        /sandbox/.lumyn/profiles \
        /sandbox/.lumyn/cache \
        /sandbox/.lumyn/pairing \
        /sandbox/.lumyn/runtime \
    && chmod 640 /sandbox/.lumyn/config.yaml \
    && chmod 640 /sandbox/.lumyn/.env \
    && for name in state.db state.db-wal state.db-shm gateway.pid gateway.lock gateway_state.json channel_directory.json; do \
        rm -f "/sandbox/.lumyn/${name}"; \
        ln -s "runtime/${name}" "/sandbox/.lumyn/${name}"; \
    done

# Pin config hash at build time for integrity verification at startup.
RUN mkdir -p /etc/vyrex \
    && sha256sum /sandbox/.lumyn/config.yaml /sandbox/.lumyn/.env \
    > /etc/vyrex/lumyn.config-hash \
    && chown root:root /etc/vyrex/lumyn.config-hash \
    && chmod 444 /etc/vyrex/lumyn.config-hash

# Backward-compatible marker for host-side shields logic on older sandboxes.
RUN sha256sum /sandbox/.lumyn/config.yaml /sandbox/.lumyn/.env \
    > /sandbox/.lumyn/.config-hash \
    && chmod 600 /sandbox/.lumyn/.config-hash \
    && chown sandbox:sandbox /sandbox/.lumyn/.config-hash

# start.sh handles privilege separation: runs as root initially, then drops
# to 'gateway' user via gosu for the agent process. See start.sh.
ENTRYPOINT ["/usr/local/bin/vyrex-start"]
CMD ["/bin/bash"]
