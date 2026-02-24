"""OpenTelemetry トレーシング初期化モジュール.

OTEL_EXPORTER_OTLP_ENDPOINT 環境変数が設定されている場合のみ
トレーシングを有効化する。未設定時はノーオペレーション。
"""

import logging
import os

logger = logging.getLogger(__name__)


def setup_tracing() -> None:
    """OpenTelemetry トレーシングをセットアップ.

    環境変数 OTEL_EXPORTER_OTLP_ENDPOINT が設定されている場合のみ
    TracerProvider + BatchSpanProcessor + OTLPSpanExporter を構成し、
    Django / requests ライブラリの自動計装を有効化する。
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT 未設定のためトレーシングを無効化")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        logger.warning(
            "OpenTelemetry パッケージが未インストールのためトレーシングを無効化"
        )
        return

    service_name = os.environ.get("OTEL_SERVICE_NAME", "django-api")
    sample_rate = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "0.25"))

    resource = Resource.create({"service.name": service_name})
    sampler = TraceIdRatioBased(sample_rate)
    provider = TracerProvider(resource=resource, sampler=sampler)

    # Docker 内部ネットワーク通信のため TLS 不要（insecure=True）
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Django HTTP リクエストの自動計装
    DjangoInstrumentor().instrument()
    # requests ライブラリの自動計装
    RequestsInstrumentor().instrument()

    logger.info(
        "OpenTelemetry トレーシングを有効化: endpoint=%s, service=%s, sample_rate=%s",
        endpoint,
        service_name,
        sample_rate,
    )
