"""
django_apiプロジェクトのASGI設定

ASGIコール可能オブジェクトをモジュールレベル変数``application``として公開します。

このファイルの詳細については以下を参照:
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Django設定モジュールを環境変数に設定
# この設定は、Djangoがどの設定ファイルを使用するかを指定
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_api.settings')

# ASGIアプリケーションインスタンスを作成
# このapplicationオブジェクトは、ASGIサーバー（Daphne、Uvicornなど）によって使用される
application = get_asgi_application()
