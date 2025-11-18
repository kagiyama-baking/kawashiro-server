"""
Swagger UIの動作確認用テスト
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


class SwaggerAPITestCase(TestCase):
    """Swagger/OpenAPI関連のテストケース"""

    def setUp(self):
        """テストの初期設定"""
        self.client = APIClient()

    def test_schema_generation(self):
        """OpenAPIスキーマが正常に生成されることをテスト"""
        url = reverse('schema')
        response = self.client.get(url)

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Content-TypeがOpenAPI仕様であることを確認
        self.assertIn('application/vnd.oai.openapi', response.get('Content-Type', ''))

        # レスポンスがJSONまたはYAML形式であることを確認
        self.assertTrue(
            response.get('Content-Type', '').startswith('application/vnd.oai.openapi') or
            response.get('Content-Type', '').startswith('application/json')
        )

    def test_swagger_ui_accessible(self):
        """Swagger UIページにアクセスできることをテスト"""
        url = reverse('swagger-ui')
        response = self.client.get(url)

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # HTMLレスポンスであることを確認
        self.assertIn('text/html', response.get('Content-Type', ''))

    def test_redoc_ui_accessible(self):
        """Redoc UIページにアクセスできることをテスト"""
        url = reverse('redoc')
        response = self.client.get(url)

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # HTMLレスポンスであることを確認
        self.assertIn('text/html', response.get('Content-Type', ''))

    def test_schema_contains_api_info(self):
        """生成されたスキーマにAPI情報が含まれていることをテスト"""
        url = reverse('schema')
        response = self.client.get(url, HTTP_ACCEPT='application/json')

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # JSONレスポンスを解析
        schema = response.json()

        # 基本的なOpenAPI構造の確認
        self.assertIn('openapi', schema)
        self.assertIn('info', schema)
        self.assertIn('paths', schema)

        # API情報の確認
        info = schema.get('info', {})
        self.assertEqual(info.get('title'), 'Kawashiro Server API')
        self.assertEqual(info.get('version'), '1.0.0')
        self.assertIn('Kawashiro Server Django API Documentation', info.get('description', ''))

    def test_schema_contains_endpoints(self):
        """生成されたスキーマに定義したエンドポイントが含まれていることをテスト"""
        url = reverse('schema')
        response = self.client.get(url, HTTP_ACCEPT='application/json')

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # JSONレスポンスを解析
        schema = response.json()
        paths = schema.get('paths', {})

        # 期待されるエンドポイントの存在確認
        expected_endpoints = [
            '/api/user/create/',
            '/api/user/token/',
            '/api/user/update/',  # 実際のURLパターンに修正
            '/api/onedrive/upload/',
            '/api/onedrive/folder/',
            '/api/onedrive/list/'
        ]

        for endpoint in expected_endpoints:
            self.assertIn(endpoint, paths, f"エンドポイント {endpoint} がスキーマに含まれていません")

    def test_schema_contains_authentication(self):
        """生成されたスキーマに認証情報が含まれていることをテスト"""
        url = reverse('schema')
        response = self.client.get(url, HTTP_ACCEPT='application/json')

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # JSONレスポンスを解析
        schema = response.json()

        # セキュリティスキーマの確認
        components = schema.get('components', {})
        security_schemes = components.get('securitySchemes', {})

        # TokenAuth認証スキーマの確認
        self.assertIn('TokenAuth', security_schemes)
        token_auth = security_schemes.get('TokenAuth', {})
        self.assertEqual(token_auth.get('type'), 'apiKey')
        self.assertEqual(token_auth.get('in'), 'header')
        self.assertEqual(token_auth.get('name'), 'Authorization')

    def test_schema_contains_tags(self):
        """生成されたスキーマにタグが含まれていることをテスト"""
        url = reverse('schema')
        response = self.client.get(url, HTTP_ACCEPT='application/json')

        # ステータスコードが200であることを確認
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # JSONレスポンスを解析
        schema = response.json()

        # タグの確認
        tags = schema.get('tags', [])
        tag_names = [tag.get('name') for tag in tags]

        # 期待されるタグの存在確認
        expected_tags = ['auth', 'users', 'onedrive']
        for tag in expected_tags:
            self.assertIn(tag, tag_names, f"タグ '{tag}' がスキーマに含まれていません")