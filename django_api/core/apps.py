from django.apps import AppConfig

# Django 管理画面でのアプリ表示順
# システム設定 → 外部サービス設定 → AIツール設定 の順で並べる
ADMIN_APP_ORDER = [
    # システム設定
    "core",
    "auth",
    "authtoken",
    # 外部サービス設定
    "msgraph_config",
    "slack",
    "tavily",
    "django_celery_beat",
    # AIツール設定
    "llm_config",
    "langfuse_integration",
    "hn_agent",
    "talk",
]


class CoreConfig(AppConfig):
    """Coreアプリケーションの設定クラス"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        """Django 管理画面の表示カスタマイズを適用する."""
        import contextlib

        from django.apps import apps
        from django.contrib.admin.sites import AdminSite

        # django-celery-beat の表示名を「Celery」に変更
        with contextlib.suppress(LookupError):
            apps.get_app_config("django_celery_beat").verbose_name = "Celery"

        # AdminSite.get_app_list を上書きし、ADMIN_APP_ORDER に従って並べる
        original_get_app_list = AdminSite.get_app_list

        def get_app_list(self, request, app_label=None):
            # Django admin.autodiscover() との race（"dictionary changed size
            # during iteration"）が起きたら、registry が安定するまでリトライ
            last_error: RuntimeError | None = None
            app_list = None
            for _ in range(5):
                try:
                    app_list = original_get_app_list(self, request, app_label)
                    break
                except RuntimeError as err:
                    last_error = err
            if app_list is None:
                raise last_error  # type: ignore[misc]

            return sorted(
                app_list,
                key=lambda a: (
                    ADMIN_APP_ORDER.index(a["app_label"])
                    if a["app_label"] in ADMIN_APP_ORDER
                    else len(ADMIN_APP_ORDER)
                ),
            )

        AdminSite.get_app_list = get_app_list
