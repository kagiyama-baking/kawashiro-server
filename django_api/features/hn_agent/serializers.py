"""HN Agent APIシリアライザ."""

from rest_framework import serializers


class WatcherResponseSerializer(serializers.Serializer):
    """Watcher実行結果."""

    stories_fetched = serializers.IntegerField(help_text="取得したストーリー数")
    new_threads = serializers.IntegerField(help_text="新規スレッド数")
    snapshots_created = serializers.IntegerField(help_text="作成したスナップショット数")
    triggered_threads = serializers.ListField(
        child=serializers.DictField(),
        help_text="閾値超えでトリガーされたスレッド一覧",
    )


class InvestigateRequestSerializer(serializers.Serializer):
    """Investigation実行リクエスト."""

    hn_id = serializers.IntegerField(help_text="調査対象のHN ID")
    skip_notify = serializers.BooleanField(
        default=True,
        help_text="Slack通知をスキップするか（デフォルト: true）",
    )


class InvestigateResponseSerializer(serializers.Serializer):
    """Investigation実行結果."""

    thread_hn_id = serializers.IntegerField(help_text="HN ID")
    thread_title = serializers.CharField(help_text="スレッドタイトル")
    steps = serializers.ListField(
        child=serializers.DictField(),
        help_text="Orchestratorの実行ステップ",
    )
    final_summary = serializers.CharField(help_text="最終サマリー")


class ThreadListSerializer(serializers.Serializer):
    """HNスレッド一覧."""

    hn_id = serializers.IntegerField()
    title = serializers.CharField()
    url = serializers.CharField()
    author = serializers.CharField()
    is_investigated = serializers.BooleanField()
    first_seen = serializers.DateTimeField()
    latest_score = serializers.IntegerField(allow_null=True)
    latest_num_comments = serializers.IntegerField(allow_null=True)
