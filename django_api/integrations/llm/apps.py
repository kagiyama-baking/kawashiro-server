"""LLM統合アプリ設定"""

from django.apps import AppConfig


class LlmConfig(AppConfig):
    """LLM統合アプリケーション設定"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations.llm"
    label = "llm_config"
    verbose_name = "LLM設定"

    def ready(self):
        """全エージェントの実行を OpenTelemetry へ記録する（Langfuse が受け取る）.

        設定は 1 つを共有する。引数なしの `instrument_all()` は実行のたびに設定を作り、
        MeterProvider が未設定の間は OpenTelemetry 側に Meter がたまり続ける。
        ここではプロキシを持つだけなので、Langfuse の初期化より先に作っても記録される。
        """
        from pydantic_ai import Agent, InstrumentationSettings

        Agent.instrument_all(InstrumentationSettings())
