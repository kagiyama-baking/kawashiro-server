"""mediaアプリのビューテスト"""
import io
import zipfile
import pytest
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


@pytest.fixture
def create_test_image():
    """テスト用の画像を作成するヘルパー関数"""
    def _create_image(format='JPEG', size=(100, 100), color='red'):
        """
        指定された形式とサイズの画像を作成

        Args:
            format: 画像フォーマット（'JPEG', 'PNG', 'WEBP'）
            size: 画像サイズ（幅, 高さ）
            color: 画像の色

        Returns:
            bytes: 画像データ
        """
        img = Image.new('RGB', size, color)
        img_io = io.BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return img_io.read()
    return _create_image


@pytest.fixture
def create_zip_file(create_test_image):
    """テスト用のZIPファイルを作成するヘルパー関数"""
    def _create_zip(files):
        """
        ファイルを含むZIPファイルを作成

        Args:
            files: ファイルのリスト [{'name': 'file.jpg', 'format': 'JPEG', 'color': 'red'}, ...]
                   または [{'name': 'file.txt', 'content': b'text content'}, ...]

        Returns:
            SimpleUploadedFile: ZIPファイルオブジェクト
        """
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_info in files:
                if 'format' in file_info:
                    # 画像ファイル
                    content = create_test_image(
                        format=file_info.get('format', 'JPEG'),
                        color=file_info.get('color', 'red')
                    )
                else:
                    # 通常のファイル
                    content = file_info.get('content', b'test content')
                zip_file.writestr(file_info['name'], content)

        zip_io.seek(0)
        return SimpleUploadedFile(
            name='test.zip',
            content=zip_io.read(),
            content_type='application/zip'
        )
    return _create_zip


@pytest.mark.api
class TestZipToPdfView:
    """ZipToPdfViewのテストクラス"""

    def test_convert_zip_to_pdf_success(self, authenticated_client, create_zip_file):
        """画像を含むZIPファイルを正常にPDFに変換できること"""
        # 3つの画像ファイルを含むZIPを作成（ファイル名順を確認するため）
        zip_file = create_zip_file([
            {'name': '03_image.jpg', 'format': 'JPEG', 'color': 'blue'},
            {'name': '01_image.png', 'format': 'PNG', 'color': 'red'},
            {'name': '02_image.webp', 'format': 'WEBP', 'color': 'green'},
        ])

        payload = {'file': zip_file}
        response = authenticated_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert 'Content-Disposition' in response
        assert 'attachment' in response['Content-Disposition']
        assert response.content.startswith(b'%PDF')

    def test_convert_zip_with_mixed_files(self, authenticated_client, create_zip_file):
        """画像ファイルとその他のファイルが混在する場合、画像のみ処理されること"""
        zip_file = create_zip_file([
            {'name': 'image1.jpg', 'format': 'JPEG', 'color': 'red'},
            {'name': 'readme.txt', 'content': b'This is a readme file'},
            {'name': 'image2.png', 'format': 'PNG', 'color': 'blue'},
            {'name': 'data.json', 'content': b'{"key": "value"}'},
        ])

        payload = {'file': zip_file}
        response = authenticated_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert response.content.startswith(b'%PDF')

    def test_convert_zip_without_images_fails(self, authenticated_client, create_zip_file):
        """画像が含まれないZIPファイルの場合はエラーになること"""
        zip_file = create_zip_file([
            {'name': 'readme.txt', 'content': b'This is a readme file'},
            {'name': 'data.json', 'content': b'{"key": "value"}'},
        ])

        payload = {'file': zip_file}
        response = authenticated_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert '画像' in response.data['error']

    def test_convert_zip_to_pdf_without_authentication_fails(self, api_client, create_zip_file):
        """認証なしでZIP→PDF変換が失敗すること"""
        zip_file = create_zip_file([
            {'name': 'image.jpg', 'format': 'JPEG', 'color': 'red'},
        ])

        payload = {'file': zip_file}
        response = api_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_convert_zip_to_pdf_without_file_fails(self, authenticated_client):
        """ファイルなしでリクエストした場合はエラーになること"""
        response = authenticated_client.post('/media/zip-to-pdf/', {}, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_convert_non_zip_file_fails(self, authenticated_client, mock_file):
        """ZIP以外のファイルをアップロードした場合はエラーになること"""
        payload = {'file': mock_file}
        response = authenticated_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_convert_sorted_images_to_pdf(self, authenticated_client, create_zip_file):
        """ファイル名が異なる順序の画像を含むZIPをPDFに変換できること"""
        # ファイル名が辞書順になるようにZIPを作成
        zip_file = create_zip_file([
            {'name': 'z_last.jpg', 'format': 'JPEG', 'color': 'blue'},
            {'name': 'a_first.jpg', 'format': 'JPEG', 'color': 'red'},
            {'name': 'm_middle.jpg', 'format': 'JPEG', 'color': 'green'},
        ])

        payload = {'file': zip_file}
        response = authenticated_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        # 実装では、ファイル名順にソートされる
        # （PDFの内容を解析するのは複雑なので、ステータスコードのみで確認）

    def test_supported_image_formats(self, authenticated_client, create_zip_file):
        """JPEG、PNG、WEBP形式の画像がすべてサポートされること"""
        zip_file = create_zip_file([
            {'name': 'image.jpg', 'format': 'JPEG', 'color': 'red'},
            {'name': 'image.jpeg', 'format': 'JPEG', 'color': 'green'},
            {'name': 'image.png', 'format': 'PNG', 'color': 'blue'},
            {'name': 'image.webp', 'format': 'WEBP', 'color': 'yellow'},
        ])

        payload = {'file': zip_file}
        response = authenticated_client.post('/media/zip-to-pdf/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
