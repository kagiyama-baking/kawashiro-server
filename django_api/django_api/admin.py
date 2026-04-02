"""django-celery-beat管理画面の日本語化."""

from django.contrib import admin
from django_celery_beat.admin import (
    ClockedScheduleAdmin,
    CrontabScheduleAdmin,
    PeriodicTaskAdmin,
    PeriodicTaskForm,
)
from django_celery_beat.models import (
    ClockedSchedule,
    CrontabSchedule,
    IntervalSchedule,
    PeriodicTask,
    SolarSchedule,
)

# ============================================================
# モデルのverbose_nameを日本語化
# ============================================================

PeriodicTask._meta.verbose_name = "定期タスク"
PeriodicTask._meta.verbose_name_plural = "定期タスク"

IntervalSchedule._meta.verbose_name = "インターバル"
IntervalSchedule._meta.verbose_name_plural = "インターバル"

CrontabSchedule._meta.verbose_name = "Cronスケジュール"
CrontabSchedule._meta.verbose_name_plural = "Cronスケジュール"

ClockedSchedule._meta.verbose_name = "時刻指定"
ClockedSchedule._meta.verbose_name_plural = "時刻指定"

# ============================================================
# フィールドのverbose_name / help_textを日本語化
# ============================================================

_PERIODIC_TASK_FIELDS = {
    "name": {
        "verbose_name": "タスク名",
        "help_text": "このタスクの識別名",
    },
    "task": {
        "verbose_name": "タスク関数",
        "help_text": '実行するCeleryタスクの関数パス（例: "hn_agent.poll_front_page"）',
    },
    "interval": {
        "verbose_name": "インターバル",
        "help_text": "インターバルスケジュール。スケジュール種別は1つだけ設定してください",
    },
    "crontab": {
        "verbose_name": "Cronスケジュール",
        "help_text": "Cronスケジュール。スケジュール種別は1つだけ設定してください",
    },
    "solar": {
        "verbose_name": "太陽イベント",
        "help_text": "太陽イベントスケジュール。スケジュール種別は1つだけ設定してください",
    },
    "clocked": {
        "verbose_name": "時刻指定",
        "help_text": "時刻指定スケジュール。スケジュール種別は1つだけ設定してください",
    },
    "args": {
        "verbose_name": "位置引数",
        "help_text": 'JSON形式の位置引数（例: ["arg1", "arg2"]）',
    },
    "kwargs": {
        "verbose_name": "キーワード引数",
        "help_text": 'JSON形式のキーワード引数（例: {"key": "value"}）',
    },
    "queue": {
        "verbose_name": "キュー",
        "help_text": "CELERY_TASK_QUEUESで定義されたキュー名。空欄でデフォルトキュー",
    },
    "exchange": {
        "verbose_name": "Exchange",
        "help_text": "AMQPルーティング用Exchange（通常は空欄）",
    },
    "routing_key": {
        "verbose_name": "ルーティングキー",
        "help_text": "AMQPルーティング用キー（通常は空欄）",
    },
    "headers": {
        "verbose_name": "メッセージヘッダー",
        "help_text": "JSON形式のAMQPメッセージヘッダー",
    },
    "priority": {
        "verbose_name": "優先度",
        "help_text": "0〜255の優先度番号（Redisでは0が最高優先度）",
    },
    "expires": {
        "verbose_name": "有効期限",
        "help_text": "この日時以降はタスクを実行しない",
    },
    "expire_seconds": {
        "verbose_name": "有効期間（秒）",
        "help_text": "この秒数が経過するとタスクを実行しない",
    },
    "one_off": {
        "verbose_name": "1回限り",
        "help_text": "有効にすると1回だけ実行して無効化される",
    },
    "start_time": {
        "verbose_name": "開始日時",
        "help_text": "この日時からタスクの実行を開始する",
    },
    "enabled": {
        "verbose_name": "有効",
        "help_text": "無効にするとスケジュールを停止します",
    },
    "last_run_at": {
        "verbose_name": "最終実行日時",
        "help_text": "最後にタスクを実行した日時",
    },
    "total_run_count": {
        "verbose_name": "累計実行回数",
        "help_text": "タスクを実行した累計回数",
    },
    "date_changed": {
        "verbose_name": "最終更新日時",
        "help_text": "この定期タスクを最後に変更した日時",
    },
    "description": {
        "verbose_name": "説明",
        "help_text": "この定期タスクの詳細説明",
    },
}

_INTERVAL_FIELDS = {
    "every": {
        "verbose_name": "間隔",
        "help_text": "タスク実行の間隔数",
    },
    "period": {
        "verbose_name": "単位",
        "help_text": "間隔の単位（例: 秒、分、時間、日）",
    },
}

_CRONTAB_FIELDS = {
    "minute": {
        "verbose_name": "分",
        "help_text": '実行する分。"*"で毎分（例: "0,30"）',
    },
    "hour": {
        "verbose_name": "時",
        "help_text": '実行する時。"*"で毎時（例: "8,20"）',
    },
    "day_of_month": {
        "verbose_name": "日",
        "help_text": '実行する日。"*"で毎日（例: "1,15"）',
    },
    "month_of_year": {
        "verbose_name": "月",
        "help_text": '実行する月（1-12）。"*"で毎月（例: "1,12"）',
    },
    "day_of_week": {
        "verbose_name": "曜日",
        "help_text": '実行する曜日。"*"で毎日、日曜=0、月曜=1（例: "1,5"で月〜金）',
    },
    "timezone": {
        "verbose_name": "タイムゾーン",
        "help_text": "Cronスケジュールのタイムゾーン（デフォルト: UTC）",
    },
}

_CLOCKED_FIELDS = {
    "clocked_time": {
        "verbose_name": "実行日時",
        "help_text": "指定した日時にタスクを実行する",
    },
}


def _apply_field_labels(model, field_map):
    """モデルのフィールドにverbose_nameとhelp_textを適用."""
    for field_name, attrs in field_map.items():
        try:
            field = model._meta.get_field(field_name)
        except Exception:  # noqa: BLE001
            continue
        if "verbose_name" in attrs:
            field.verbose_name = attrs["verbose_name"]
        if "help_text" in attrs:
            field.help_text = attrs["help_text"]


_apply_field_labels(PeriodicTask, _PERIODIC_TASK_FIELDS)
_apply_field_labels(IntervalSchedule, _INTERVAL_FIELDS)
_apply_field_labels(CrontabSchedule, _CRONTAB_FIELDS)
_apply_field_labels(ClockedSchedule, _CLOCKED_FIELDS)


# ============================================================
# Admin再登録（日本語化されたフィールドを反映）
# ============================================================

admin.site.unregister(PeriodicTask)
admin.site.unregister(IntervalSchedule)
admin.site.unregister(CrontabSchedule)
admin.site.unregister(SolarSchedule)  # 管理画面には再登録しない（未使用）
admin.site.unregister(ClockedSchedule)


@admin.register(PeriodicTask)
class JaPeriodicTaskAdmin(PeriodicTaskAdmin):
    """定期タスク管理（日本語化）."""

    form = PeriodicTaskForm


@admin.register(IntervalSchedule)
class JaIntervalScheduleAdmin(admin.ModelAdmin):
    """インターバルスケジュール管理（日本語化）."""

    list_display = ("every", "period")


@admin.register(CrontabSchedule)
class JaCrontabScheduleAdmin(CrontabScheduleAdmin):
    """Cronスケジュール管理（日本語化）."""


@admin.register(ClockedSchedule)
class JaClockedScheduleAdmin(ClockedScheduleAdmin):
    """時刻指定スケジュール管理（日本語化）."""
