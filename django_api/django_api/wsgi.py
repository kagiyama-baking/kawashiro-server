"""
django_apiプロジェクトのWSGI設定

WSGIアプリケーションをモジュールレベル変数 ``application`` として公開します。

このファイルの詳細については、以下を参照してください：
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Django設定モジュールを環境変数に設定（デフォルト値を指定）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_api.settings')

# WSGIアプリケーションインスタンスを取得
application = get_wsgi_application()
