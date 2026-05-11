#!/bin/bash
echo "=== PradyOS Integration Verification ==="

echo "[1] Checking Vyrex..."
if [ -d "/opt/vyrex" ]; then
  echo "  ✓ Vyrex installed at /opt/vyrex"
  python3 -c "import vyrex; print('  ✓ Vyrex importable')" 2>/dev/null || echo "  ✗ Vyrex not importable"
else
  echo "  ✗ Vyrex NOT installed"
fi

echo "[2] Checking Lumyn Agent..."
if [ -d "/opt/lumyn-agent" ]; then
  echo "  ✓ Lumyn Agent installed at /opt/lumyn-agent"
  lumyn --version 2>/dev/null && echo "  ✓ lumyn CLI works" || echo "  ✗ lumyn CLI not in PATH"
else
  echo "  ✗ Lumyn Agent NOT installed"
fi

echo "[3] Checking Kryos..."
if [ -d "/opt/prax-agent" ]; then
  echo "  ✓ Kryos installed at /opt/prax-agent"
  kryos --version 2>/dev/null && echo "  ✓ kryos CLI works" || echo "  ✗ kryos CLI not in PATH"
else
  echo "  ✗ Prax Agent NOT installed"
fi

echo "[4] Checking systemd services..."
for svc in vyrex prax-agent kryos-firstboot ydotoold; do
  systemctl is-enabled $svc 2>/dev/null && echo "  ✓ $svc enabled" || echo "  ✗ $svc NOT enabled"
done

echo "[5] Checking swarm config..."
if [ -f "/etc/kryos/swarm-default.yaml" ]; then
  echo "  ✓ swarm-default.yaml exists"
  grep -q "inference_backend: vyrex" /etc/kryos/swarm-default.yaml && \
    echo "  ✓ Vyrex set as inference backend" || echo "  ✗ inference_backend wrong"
  grep -q "lumyn-primary" /etc/kryos/swarm-default.yaml && \
    echo "  ✓ Lumyn agents configured" || echo "  ✗ Lumyn agents missing"
else
  echo "  ✗ swarm-default.yaml MISSING"
fi

echo "=== Verification Complete ==="
