#!/bin/bash

# Prometheus Setup Script for Video AI Studio

set -e

echo "🚀 Setting up Prometheus monitoring..."

# Install Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.47.0/prometheus-2.47.0.linux-amd64.tar.gz
tar xvfz prometheus-2.47.0.linux-amd64.tar.gz
cd prometheus-2.47.0.linux-amd64

# Create systemd service
cat > /etc/systemd/system/prometheus.service << EOF
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \
    --config.file /etc/prometheus/prometheus.yml \
    --storage.tsdb.path /var/lib/prometheus/ \
    --web.console.templates=/etc/prometheus/consoles \
    --web.console.libraries=/etc/prometheus/console_libraries

[Install]
WantedBy=multi-user.target
EOF

# Create Prometheus user
useradd --no-create-home --shell /bin/false prometheus

# Create directories
mkdir -p /etc/prometheus
mkdir -p /var/lib/prometheus

# Copy binaries
cp prometheus promtool /usr/local/bin/
cp -r consoles console_libraries /etc/prometheus/

# Configure Prometheus
cat > /etc/prometheus/prometheus.yml << EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/rules.yml

scrape_configs:
  - job_name: 'video-ai-studio'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['localhost:9100']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['localhost:9121']

  - job_name: 'postgres-exporter'
    static_configs:
      - targets: ['localhost:9187']

  - job_name: 'nginx-exporter'
    static_configs:
      - targets: ['localhost:9113']
EOF

# Create alerting rules
cat > /etc/prometheus/rules.yml << EOF
groups:
  - name: video_ai_studio
    rules:
    - alert: HighErrorRate
      expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "High error rate detected"
        description: "Error rate is {{ \$value }} for service {{ \$labels.service }}"

    - alert: HighQueueLength
      expr: processing_queue_length > 100
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Processing queue is long"
        description: "Queue length is {{ \$value }}"

    - alert: HighResponseTime
      expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High response time detected"
        description: "95th percentile response time is {{ \$value }}s"

    - alert: ServiceDown
      expr: up == 0
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "Service {{ \$labels.job }} is down"
        description: "{{ \$labels.instance }} of job {{ \$labels.job }} has been down for more than 1 minute."

    - alert: HighMemoryUsage
      expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.9
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High memory usage on {{ \$labels.instance }}"
        description: "Memory usage is {{ \$value }}"

    - alert: HighCPUUsage
      expr: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "High CPU usage on {{ \$labels.instance }}"
        description: "CPU usage is {{ \$value }}%"

    - alert: LowDiskSpace
      expr: (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 10
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Low disk space on {{ \$labels.instance }}"
        description: "Disk space is only {{ \$value }}% free on {{ \$labels.mountpoint }}"

    - alert: HighAICosts
      expr: rate(ai_processing_cost_total[1h]) > 100
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "High AI processing costs detected"
        description: "AI costs are {{ \$value }} USD/hour"

    - alert: ManyFailedVideos
      expr: rate(videos_processed_total{status="failed"}[1h]) > 10
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "High video processing failure rate"
        description: "{{ \$value }} videos failed in the last hour"

    - alert: CreditDepletion
      expr: user_credits_remaining < 10
      for: 1h
      labels:
        severity: info
      annotations:
        summary: "User credits running low"
        description: "User {{ \$labels.user_id }} has only {{ \$value }} credits remaining"
EOF

# Set permissions
chown -R prometheus:prometheus /etc/prometheus
chown -R prometheus:prometheus /var/lib/prometheus

# Enable and start service
systemctl daemon-reload
systemctl enable prometheus
systemctl start prometheus

echo "✅ Prometheus setup complete!"