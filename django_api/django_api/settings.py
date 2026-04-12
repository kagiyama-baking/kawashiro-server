"""
django_apiプロジェクトのDjango設定

'django-admin startproject'によってDjango 5.2.7を使用して生成

このファイルの詳細については以下を参照:
https://docs.djangoproject.com/en/5.2/topics/settings/

設定とその値の完全なリストについては以下を参照:
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# ============================================================
# 基本設定
# ============================================================

# プロジェクトのベースディレクトリへのパス
# このファイルから2つ上のディレクトリ（プロジェクトルート）を指定
BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# セキュリティ設定
# ============================================================

# クイックスタート開発設定 - 本番環境には不適切
# 参照: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# 環境変数から取得（必須）
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is not set. "
        "Please set SECRET_KEY in your .env file (例: .envファイルに「SECRET_KEY=your-secret-key-here」を追加してください)。"
    )

# DEBUGモード（環境変数が'True'の場合のみTrue）
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

# 暗号化キー（データベースに保存する機密情報の暗号化に使用）
# 32文字以上のランダムな文字列を設定してください
# 例: openssl rand -base64 32 で生成
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# ALLOWED_HOSTSをカンマ区切りから配列に変換
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost").split(",")
    if host.strip()  # 空文字列を除外
]

# リバースプロキシ（Traefik）経由のHTTPS判定
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CSRF信頼済みオリジン（Traefik経由のドメイン）
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# ============================================================
# アプリケーション設定
# ============================================================

# インストール済みアプリケーションの定義
INSTALLED_APPS = [
    # Djangoの標準アプリケーション
    "django.contrib.admin",  # 管理画面
    "django.contrib.auth",  # 認証フレームワーク
    "django.contrib.contenttypes",  # コンテンツタイプフレームワーク
    "django.contrib.sessions",  # セッションフレームワーク
    "django.contrib.messages",  # メッセージフレームワーク
    "django.contrib.staticfiles",  # 静的ファイル管理
    # サードパーティアプリケーション
    "rest_framework",  # Django REST framework
    "rest_framework.authtoken",  # トークン認証
    "drf_spectacular",  # OpenAPI/Swagger documentation
    # カスタムアプリケーション
    "core",  # ユーザー認証などのコア機能
    "user",  # ユーザーモデルのApp
    "integrations.msgraph",  # Microsoft Graph API設定・クライアント
    "integrations.llm",  # LLM API設定・クライアント
    "integrations.langfuse",  # Langfuseプロンプト参照管理
    "integrations.onedrive",  # OneDrive連携機能
    "integrations.outlook",  # Outlook Calendar連携機能
    "features.media",  # 画像処理などのメディア関連機能
    "integrations.tts",  # Text-to-Speech機能
    "integrations.weather",  # 気象庁天気予報機能
    "features.talk",  # 会話生成機能
    "health",  # ヘルスチェック
    # タスクキュー
    "django_celery_beat",  # Celery Beat定期タスクスケジューラ
    # HN Agent
    "integrations.hn",  # Hacker News Algolia API連携
    "integrations.tavily",  # Tavily Web検索API連携
    "integrations.slack",  # Slack通知連携
    "features.hn_agent",  # HN監視・分析エージェント
]

# ミドルウェアの設定
# リクエスト/レスポンス処理のフックポイント
MIDDLEWARE = [
    "health.middleware.HealthCheckMiddleware",  # ヘルスチェック（ALLOWED_HOSTSチェック前に応答）
    "django.middleware.security.SecurityMiddleware",  # セキュリティヘッダー追加
    "whitenoise.middleware.WhiteNoiseMiddleware",  # 静的ファイル配信（SecurityMiddlewareの直後に配置）
    "django.contrib.sessions.middleware.SessionMiddleware",  # セッション管理
    "django.middleware.common.CommonMiddleware",  # 共通処理（URLの正規化など）
    "django.middleware.csrf.CsrfViewMiddleware",  # CSRF攻撃からの保護
    "django.contrib.auth.middleware.AuthenticationMiddleware",  # ユーザー認証
    "django.contrib.messages.middleware.MessageMiddleware",  # メッセージフレームワーク
    "django.middleware.clickjacking.XFrameOptionsMiddleware",  # クリックジャッキング防止
]

# URLルーティングの設定
ROOT_URLCONF = "django_api.urls"

# テンプレートエンジンの設定
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],  # テンプレートディレクトリ（追加のディレクトリがある場合はここに指定）
        "APP_DIRS": True,  # 各アプリケーションのtemplatesディレクトリを検索
        "OPTIONS": {
            # コンテキストプロセッサ（テンプレートに自動的に渡される変数）
            "context_processors": [
                "django.template.context_processors.request",  # requestオブジェクトを提供
                "django.contrib.auth.context_processors.auth",  # ユーザー認証情報を提供
                "django.contrib.messages.context_processors.messages",  # メッセージを提供
            ],
        },
    },
]

# WSGIアプリケーションのパス
WSGI_APPLICATION = "django_api.wsgi.application"


# ============================================================
# データベース設定
# ============================================================
# 参照: https://docs.djangoproject.com/en/5.2/ref/settings/#databases

if os.getenv("DB_ENGINE"):
    _db_password = os.getenv("DB_PASSWORD")
    if not _db_password:
        raise ValueError("DB_PASSWORD is required when DB_ENGINE is set.")
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DB_ENGINE"),
            "NAME": os.getenv("DB_NAME", "kawashiro"),
            "USER": os.getenv("DB_USER", "kawashiro"),
            "PASSWORD": _db_password,
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ============================================================
# パスワード検証設定
# ============================================================
# 参照: https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        # ユーザー属性との類似性チェック
        # ユーザー名やメールアドレスに似たパスワードを禁止
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        # 最小文字数チェック（デフォルト: 8文字）
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        # 一般的なパスワードチェック
        # よく使われる弱いパスワードを禁止
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        # 数字のみのパスワードを禁止
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ============================================================
# 国際化設定
# ============================================================
# 参照: https://docs.djangoproject.com/en/5.2/topics/i18n/

# デフォルトの言語コード
LANGUAGE_CODE = "ja"

# タイムゾーン設定
# 日本時間の場合は 'Asia/Tokyo' に変更
TIME_ZONE = "Asia/Tokyo"

# 国際化機能の有効化
USE_I18N = True

# タイムゾーン対応の有効化
# データベースにUTCで保存し、表示時に変換
USE_TZ = True


# ============================================================
# 静的ファイル設定
# ============================================================
# 参照: https://docs.djangoproject.com/en/5.2/howto/static-files/

# 静的ファイル（CSS、JavaScript、画像）のURL
STATIC_URL = "/static/"

# 本番環境で静的ファイルを集約するディレクトリ
STATIC_ROOT = BASE_DIR / "staticfiles"

# 開発環境用の追加静的ファイルディレクトリ
# STATICFILES_DIRS = [
#     BASE_DIR / 'static',
# ]

# WhiteNoise設定
# 静的ファイルの圧縮とキャッシュを有効化
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# ============================================================
# その他の設定
# ============================================================

# プライマリキーのデフォルトフィールドタイプ
# BigAutoFieldは64ビット整数を使用
# 参照: https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# カスタムユーザーモデルの指定
# アプリ名.モデル名の形式で指定
AUTH_USER_MODEL = "core.User"

# ============================================================
# REST Framework設定
# ============================================================
REST_FRAMEWORK = {
    # デフォルトのAPIスキーマクラスをdrf-spectacularに設定
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # デフォルトの認証クラス
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # デフォルトのパーミッションクラス
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # レート制限（ブルートフォース対策）
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10/minute",
    },
}

# ============================================================
# drf-spectacular設定 (OpenAPI/Swagger)
# ============================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "Kawashiro Server API",
    "DESCRIPTION": "Kawashiro Server Django API Documentation",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,  # スキーマエンドポイントを含めない
    # APIのセキュリティスキーマ定義
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/",
    # Swagger UIの設定
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,  # 認証情報を保持
        "displayOperationId": False,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
    },
    # セキュリティ定義
    "SECURITY": [{"TokenAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "TokenAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": 'Token-based authentication with required prefix "Token"',
            }
        }
    },
    # タグの説明
    "TAGS": [
        {"name": "auth", "description": "認証関連のAPI"},
        {"name": "users", "description": "ユーザー管理API"},
        {"name": "onedrive", "description": "OneDrive連携API"},
        {"name": "outlook", "description": "Outlook Calendar連携API"},
        {"name": "media", "description": "画像処理などのメディア関連API"},
        {"name": "tts", "description": "Text-to-Speech読み上げAPI"},
        {"name": "weather", "description": "気象庁天気予報API"},
        {"name": "hn-agent", "description": "HN監視・分析エージェントAPI"},
        {"name": "talk", "description": "会話生成API"},
    ],
    # Swagger UIのAPIベースURL（nginx リバースプロキシが /api/ プレフィックスを除去して転送）
    "SERVERS": [{"url": "/api", "description": "API"}],
}

# ============================================================
# Celery設定
# ============================================================
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ============================================================
# TTS設定
# ============================================================
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://sbv2-api:5000")
TTS_TIMEOUT = int(os.getenv("TTS_TIMEOUT", "120"))
