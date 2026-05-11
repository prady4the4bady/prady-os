#!/usr/bin/env bash
# sign_iso.sh — Prady OS Release ISO Signing
#
# Generates release verification artifacts for a built ISO:
#   1) SHA256 sidecar file
#   2) release-checksums.txt manifest
#   3) Optional GPG detached signature (.sig)
#
# Usage:
#   ./sign_iso.sh <path/to/kryos-os.iso>
#
# Optional env vars:
#   KRYOS_GPG_KEY_ID   GPG key id/email to sign with
#   REQUIRE_GPG        Set to 1 to fail when GPG signing is unavailable

set -euo pipefail

ISO_PATH="${1:-}"
REQUIRE_GPG="${REQUIRE_GPG:-0}"
GPG_KEY_ID="${KRYOS_GPG_KEY_ID:-}"

if [ -z "${ISO_PATH}" ]; then
    echo "Usage: $0 <path/to/kryos-os.iso>"
    exit 1
fi

if [ ! -f "${ISO_PATH}" ]; then
    echo "Error: ISO not found: ${ISO_PATH}"
    exit 1
fi

ISO_ABS="$(cd "$(dirname "${ISO_PATH}")" && pwd)/$(basename "${ISO_PATH}")"
OUT_DIR="$(dirname "${ISO_ABS}")"
ISO_NAME="$(basename "${ISO_ABS}")"
SHA_FILE="${OUT_DIR}/${ISO_NAME%.iso}.sha256"
MANIFEST_FILE="${OUT_DIR}/release-checksums.txt"
SIG_FILE="${ISO_ABS}.sig"

echo "[SIGN] Building release artifacts for ${ISO_NAME}"

SHA256="$(sha256sum "${ISO_ABS}" | awk '{print $1}')"
echo "${SHA256}  ${ISO_NAME}" | tee "${SHA_FILE}" > /dev/null
cp "${SHA_FILE}" "${MANIFEST_FILE}"

if command -v gpg >/dev/null 2>&1 && [ -n "${GPG_KEY_ID}" ]; then
    echo "[SIGN] Creating detached GPG signature with key ${GPG_KEY_ID}"
    gpg --batch --yes --armor --local-user "${GPG_KEY_ID}" --output "${SIG_FILE}" --detach-sign "${ISO_ABS}"
    echo "[SIGN] Signature generated: ${SIG_FILE}"
elif [ "${REQUIRE_GPG}" = "1" ]; then
    echo "Error: GPG signing is required but unavailable (missing gpg or KRYOS_GPG_KEY_ID)."
    exit 1
else
    echo "[SIGN] GPG signing skipped (set KRYOS_GPG_KEY_ID to enable)."
fi

echo "[SIGN] SHA256: ${SHA256}"
echo "[SIGN] Manifest: ${MANIFEST_FILE}"
echo "[SIGN] Verification command:"
echo "       sha256sum --check ${SHA_FILE}"
