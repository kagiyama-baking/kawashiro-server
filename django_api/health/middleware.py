"""ヘルスチェックミドルウェア

ALLOWED_HOSTSチェックより先にヘルスチェックリクエストを処理する。
ミドルウェアチェーンの先頭に配置することで、SecurityMiddlewareや
CommonMiddlewareによるHostヘッダー検証をバイパスする。
"""

from django.http import JsonResponse


class HealthCheckMiddleware:
    """ヘルスチェック用ミドルウェア"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
