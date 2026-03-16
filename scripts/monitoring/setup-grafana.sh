#!/bin/bash

# Grafana Setup Script for Video AI Studio

set -e

echo "📊 Setting up Grafana dashboard..."

# Install Grafana
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
apt-get update
apt-get install -y grafana

# Configure Grafana
cat > /etc/grafana/grafana.ini << EOF
[server]
http_addr = 0.0.0.0
http_port = 3000
domain = monitoring.videoaistudio.com
root_url = %(protocol)s://%(domain)s:%(http_port)s/
serve_from_sub_path = false

[database]
type = sqlite3
path = grafana.db

[security]
admin_user = admin
admin_password = changeme123
secret_key = $(openssl rand -hex 20)

[session]
provider = file

[analytics]
reporting_enabled = false
check_for_updates = false

[log]
mode = console file
level = info

[alerting]
enabled = true
execute_alerts = true

[unified_alerting]
enabled = true

[feature_toggles]
enable = publicDashboards
EOF

# Install plugins
grafana-cli plugins install grafana-piechart-panel
grafana-cli plugins install marcusolsson-hourly-heatmap-panel
grafana-cli plugins install marcusolsson-treemap-panel

# Create dashboard directory
mkdir -p /etc/grafana/provisioning/dashboards
mkdir -p /etc/grafana/provisioning/datasources

# Configure Prometheus data source
cat > /etc/grafana/provisioning/datasources/prometheus.yml << EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://localhost:9090
    isDefault: true
    editable: true
EOF

# Create dashboard configurations
cat > /etc/grafana/provisioning/dashboards/dashboards.yml << EOF
apiVersion: 1

providers:
  - name: 'Video AI Studio'
    orgId: 1
    folder: 'Video AI Studio'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    options:
      path: /etc/grafana/dashboards
EOF

# Create dashboards directory
mkdir -p /etc/grafana/dashboards

# Create Video AI Studio dashboard
cat > /etc/grafana/dashboards/video-ai-studio.json << 'EOF'
{
  "dashboard": {
    "id": null,
    "title": "Video AI Studio - Overview",
    "tags": ["video-ai", "monitoring"],
    "style": "dark",
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "System Health",
        "type": "stat",
        "gridPos": {"h": 3, "w": 6, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "up",
            "format": "time_series",
            "instant": true
          }
        ],
        "fieldConfig": {
          "defaults": {
            "color": {"mode": "thresholds"},
            "mappings": [],
            "thresholds": {
              "steps": [
                {"color": "red", "value": null},
                {"color": "green", "value": 1}
              ]
            }
          }
        }
      },
      {
        "id": 2,
        "title": "CPU Usage",
        "type": "gauge",
        "gridPos": {"h": 3, "w": 6, "x": 6, "y": 0},
        "targets": [
          {
            "expr": "100 - (avg by(instance) (irate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "thresholds": {
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 70},
                {"color": "red", "value": 90}
              ]
            }
          }
        }
      },
      {
        "id": 3,
        "title": "Memory Usage",
        "type": "gauge",
        "gridPos": {"h": 3, "w": 6, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "thresholds": {
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 70},
                {"color": "red", "value": 90}
              ]
            }
          }
        }
      },
      {
        "id": 4,
        "title": "HTTP Requests",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 3},
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "reqps"
          }
        }
      },
      {
        "id": 5,
        "title": "Video Processing",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 3},
        "targets": [
          {
            "expr": "rate(videos_processed_total[5m])",
            "legendFormat": "{{tier}} {{status}}",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "cpm"
          }
        }
      },
      {
        "id": 6,
        "title": "AI Processing Costs",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 11},
        "targets": [
          {
            "expr": "rate(ai_processing_cost_total[1h])",
            "legendFormat": "{{service}}",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "currencyUSD",
            "decimals": 4
          }
        }
      },
      {
        "id": 7,
        "title": "User Tier Distribution",
        "type": "piechart",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 11},
        "targets": [
          {
            "expr": "count by(tier) (user_signups_total)",
            "format": "time_series"
          }
        ]
      },
      {
        "id": 8,
        "title": "Queue Length",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 19},
        "targets": [
          {
            "expr": "processing_queue_length",
            "format": "time_series"
          }
        ]
      },
      {
        "id": 9,
        "title": "Response Time (95th percentile)",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 19},
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s"
          }
        }
      },
      {
        "id": 10,
        "title": "Error Rate",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 27},
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m]) * 100",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent"
          }
        }
      },
      {
        "id": 11,
        "title": "Database Connections",
        "type": "stat",
        "gridPos": {"h": 3, "w": 6, "x": 0, "y": 35},
        "targets": [
          {
            "expr": "database_connections_current",
            "format": "time_series",
            "instant": true
          }
        ]
      },
      {
        "id": 12,
        "title": "Redis Memory Usage",
        "type": "gauge",
        "gridPos": {"h": 3, "w": 6, "x": 6, "y": 35},
        "targets": [
          {
            "expr": "redis_memory_used_bytes / redis_memory_max_bytes * 100",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent"
          }
        }
      }
    ],
    "time": {"from": "now-6h", "to": "now"},
    "refresh": "30s"
  },
  "folderId": 0,
  "overwrite": true
}
EOF

# Create business metrics dashboard
cat > /etc/grafana/dashboards/business-metrics.json << 'EOF'
{
  "dashboard": {
    "id": null,
    "title": "Video AI Studio - Business Metrics",
    "tags": ["video-ai", "business"],
    "panels": [
      {
        "id": 1,
        "title": "Monthly Recurring Revenue",
        "type": "stat",
        "gridPos": {"h": 3, "w": 6, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "sum(rate(payment_received_total{is_recurring=\"true\"}[30d])) * 30 * 12",
            "format": "time_series",
            "instant": true
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "currencyUSD",
            "decimals": 0
          }
        }
      },
      {
        "id": 2,
        "title": "Active Users",
        "type": "stat",
        "gridPos": {"h": 3, "w": 6, "x": 6, "y": 0},
        "targets": [
          {
            "expr": "active_users_current",
            "format": "time_series",
            "instant": true
          }
        ]
      },
      {
        "id": 3,
        "title": "Videos Processed Today",
        "type": "stat",
        "gridPos": {"h": 3, "w": 6, "x": 12, "y": 0},
        "targets": [
          {
            "expr": "increase(videos_processed_total[1d])",
            "format": "time_series",
            "instant": true
          }
        ]
      },
      {
        "id": 4,
        "title": "Revenue by Tier",
        "type": "barchart",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 3},
        "targets": [
          {
            "expr": "sum by(tier) (rate(payment_received_total[30d])) * 30",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "currencyUSD"
          }
        }
      },
      {
        "id": 5,
        "title": "User Growth",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 3},
        "targets": [
          {
            "expr": "increase(user_signups_total[7d])",
            "legendFormat": "New Users",
            "format": "time_series"
          }
        ]
      },
      {
        "id": 6,
        "title": "Tier Upgrades",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 11},
        "targets": [
          {
            "expr": "rate(tier_upgrades_total[1d])",
            "legendFormat": "{{from_tier}} to {{to_tier}}",
            "format": "time_series"
          }
        ]
      },
      {
        "id": 7,
        "title": "Cost per Video",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 11},
        "targets": [
          {
            "expr": "rate(ai_processing_cost_total[1h]) / rate(videos_processed_total[1h])",
            "format": "time_series"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "currencyUSD",
            "decimals": 3
          }
        }
      },
      {
        "id": 8,
        "title": "Profit Margin",
        "type": "gauge",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 19},
        "targets": [
          {
            "expr": "(1 - (rate(ai_processing_cost_total[30d]) / sum(rate(payment_received_total[30d])))) * 100",
            "format": "time_series",
            "instant": true
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "thresholds": {
              "steps": [
                {"color": "red", "value": null},
                {"color": "yellow", "value": 80},
                {"color": "green", "value": 90}
              ]
            }
          }
        }
      }
    ]
  }
}
EOF

# Set permissions
chown -R grafana:grafana /etc/grafana
chown -R grafana:grafana /var/lib/grafana

# Enable and start Grafana
systemctl daemon-reload
systemctl enable grafana-server
systemctl start grafana-server

echo "✅ Grafana setup complete!"
echo "📊 Access Grafana at: http://localhost:3000"
echo "👤 Default credentials: admin / changeme123"