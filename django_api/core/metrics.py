"""Prometheus カスタムメトリクス定義."""

from prometheus_client import Histogram

# 外部API呼び出しの所要時間
EXTERNAL_API_DURATION = Histogram(
    "django_external_api_duration_seconds",
    "外部API呼び出しの所要時間（秒）",
    labelnames=["service", "method"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
