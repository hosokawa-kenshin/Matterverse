# Multi-stage build for Matterverse application
# Stage 1: Build environment for Matter SDK
FROM ubuntu:24.04 AS builder

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    pkg-config \
    libssl-dev \
    libdbus-1-dev \
    libglib2.0-dev \
    libavahi-client-dev \
    ninja-build \
    python3-dev \
    unzip \
    libgirepository1.0-dev \
    libcairo2-dev \
    libreadline-dev \
    generate-ninja \
    zip \
    && rm -rf /var/lib/apt/lists/*

# Clone and build Matter SDK
WORKDIR /app
RUN git clone --depth 1 --branch factory_iot https://github.com/hosokawa-kenshin/connectedhomeip.git
WORKDIR /app/connectedhomeip

# Bootstrap and activate environment
RUN ./scripts/checkout_submodules.py --allow-changing-global-git-config --shallow --platform linux
RUN bash scripts/bootstrap.sh
RUN bash -c "source scripts/activate.sh && gn gen out/host && ninja -C out/host chip-tool"

# Stage 2: Production environment
FROM ubuntu:24.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    libssl3 \
    libdbus-1-3 \
    libglib2.0-0 \
    libavahi-client3 \
    libreadline8 \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy built chip-tool from builder stage
COPY --from=builder /app/connectedhomeip/out/host/chip-tool /usr/local/bin/chip-tool
COPY --from=builder /etc/chip/ /etc/chip/
RUN chmod +x /usr/local/bin/chip-tool

# Create non-root user
RUN groupadd -r matterverse && useradd -r -g matterverse -m matterverse

# Set working directory
WORKDIR /app

RUN mkdir -p /app/db /app/commissioning_dir

# Copy application source
COPY . .

# Copy Matter data model files from builder stage
COPY --from=builder /app/connectedhomeip/src/app/zap-templates/zcl/data-model/chip/ ./data_model/
COPY --from=builder /app/connectedhomeip/credentials/development/paa-root-certs ./paa-root-certs/

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Set ownership
RUN chown -R matterverse:matterverse /app

# Switch to non-root user
USER matterverse

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["python3", "main.py"]
