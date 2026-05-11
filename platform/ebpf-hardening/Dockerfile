FROM ubuntu:22.04

# Install dependencies for eBPF toolchain, kernel headers, libbpf
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    clang \
    llvm \
    libelf-dev \
    linux-headers-generic \
    libbpf-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Compile eBPF programs at image build time
WORKDIR /app/programs
RUN make clean || true && make

WORKDIR /app

# Run ebpf_loader service
EXPOSE 8118
CMD ["python3", "-m", "uvicorn", "ebpf_loader:app", "--host", "0.0.0.0", "--port", "8118"]
