"""HN Agentアプリ設定."""

from django.apps import AppConfig


class HNAgentConfig(AppConfig):
    """Hacker News監視・分析エージェントアプリ設定."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "features.hn_agent"
    label = "hn_agent"
    verbose_name = "HN Agent"
