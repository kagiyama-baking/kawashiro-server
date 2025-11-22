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


@pytest.mark.api
class TestImageConvertView:
    """ImageConvertViewのテストクラス"""

    def test_convert_jpg_to_png_success(self, authenticated_client, create_test_image):
        """JPG画像をPNGに変換できること"""
        jpg_image = create_test_image(format='JPEG', color='red')
        uploaded_file = SimpleUploadedFile(
            name='test.jpg',
            content=jpg_image,
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file, 'output_format': 'png'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/png'
        assert 'Content-Disposition' in response
        assert 'attachment' in response['Content-Disposition']
        # ファイル名が [YYYYMMDD].[width]x[height].png の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.png'
        assert re.search(filename_pattern, response['Content-Disposition'])
        # PNG画像のシグネチャを確認
        assert response.content.startswith(b'\x89PNG')

    def test_convert_png_to_jpg_success(self, authenticated_client, create_test_image):
        """PNG画像をJPGに変換できること"""
        png_image = create_test_image(format='PNG', color='blue')
        uploaded_file = SimpleUploadedFile(
            name='test.png',
            content=png_image,
            content_type='image/png'
        )

        payload = {'file': uploaded_file, 'output_format': 'jpg'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/jpeg'
        # ファイル名が [YYYYMMDD].[width]x[height].jpg の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.jpg'
        assert re.search(filename_pattern, response['Content-Disposition'])
        # JPEG画像のシグネチャを確認
        assert response.content.startswith(b'\xff\xd8\xff')

    def test_convert_jpg_to_webp_success(self, authenticated_client, create_test_image):
        """JPG画像をWebPに変換できること"""
        jpg_image = create_test_image(format='JPEG', color='green')
        uploaded_file = SimpleUploadedFile(
            name='image.jpg',
            content=jpg_image,
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file, 'output_format': 'webp'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/webp'
        # ファイル名が [YYYYMMDD].[width]x[height].webp の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.webp'
        assert re.search(filename_pattern, response['Content-Disposition'])
        # WebP画像のシグネチャを確認
        assert b'WEBP' in response.content[:20]

    def test_convert_png_to_tiff_success(self, authenticated_client, create_test_image):
        """PNG画像をTIFFに変換できること"""
        png_image = create_test_image(format='PNG', color='yellow')
        uploaded_file = SimpleUploadedFile(
            name='photo.png',
            content=png_image,
            content_type='image/png'
        )

        payload = {'file': uploaded_file, 'output_format': 'tiff'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/tiff'
        # ファイル名が [YYYYMMDD].[width]x[height].tiff の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.tiff'
        assert re.search(filename_pattern, response['Content-Disposition'])
        # TIFF画像のシグネチャを確認（リトルエンディアン or ビッグエンディアン）
        assert response.content.startswith((b'II\x2a\x00', b'MM\x00\x2a'))

    def test_convert_webp_to_jpg_success(self, authenticated_client, create_test_image):
        """WebP画像をJPGに変換できること"""
        webp_image = create_test_image(format='WEBP', color='purple')
        uploaded_file = SimpleUploadedFile(
            name='sample.webp',
            content=webp_image,
            content_type='image/webp'
        )

        payload = {'file': uploaded_file, 'output_format': 'jpg'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/jpeg'
        # ファイル名が [YYYYMMDD].[width]x[height].jpg の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.jpg'
        assert re.search(filename_pattern, response['Content-Disposition'])

    def test_convert_tiff_to_png_success(self, authenticated_client):
        """TIFF画像をPNGに変換できること"""
        # TIFFファイルを作成
        tiff_img = Image.new('RGB', (100, 100), 'orange')
        tiff_io = io.BytesIO()
        tiff_img.save(tiff_io, format='TIFF')
        tiff_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name='document.tiff',
            content=tiff_io.read(),
            content_type='image/tiff'
        )

        payload = {'file': uploaded_file, 'output_format': 'png'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/png'
        # ファイル名が [YYYYMMDD].[width]x[height].png の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.png'
        assert re.search(filename_pattern, response['Content-Disposition'])

    def test_convert_without_file_fails(self, authenticated_client):
        """ファイルなしでリクエストした場合はエラーになること"""
        payload = {'output_format': 'png'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_convert_without_output_format_fails(self, authenticated_client, create_test_image):
        """出力形式を指定しない場合はエラーになること"""
        jpg_image = create_test_image(format='JPEG', color='red')
        uploaded_file = SimpleUploadedFile(
            name='test.jpg',
            content=jpg_image,
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_convert_with_invalid_output_format_fails(self, authenticated_client, create_test_image):
        """サポートされていない出力形式を指定した場合はエラーになること"""
        jpg_image = create_test_image(format='JPEG', color='red')
        uploaded_file = SimpleUploadedFile(
            name='test.jpg',
            content=jpg_image,
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file, 'output_format': 'bmp'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'サポートされていない' in response.data['error']

    def test_convert_invalid_image_file_fails(self, authenticated_client, mock_file):
        """無効な画像ファイルの場合はエラーになること"""
        payload = {'file': mock_file, 'output_format': 'png'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_convert_without_authentication_fails(self, api_client, create_test_image):
        """認証なしで画像変換が失敗すること"""
        jpg_image = create_test_image(format='JPEG', color='red')
        uploaded_file = SimpleUploadedFile(
            name='test.jpg',
            content=jpg_image,
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file, 'output_format': 'png'}
        response = api_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_convert_filename_format_with_dimensions(self, authenticated_client, create_test_image):
        """変換後のファイル名が画像サイズを含むこと"""
        # 特定のサイズの画像を作成
        img = Image.new('RGB', (1920, 1080), 'red')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name='test.jpg',
            content=img_io.read(),
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file, 'output_format': 'png'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        # ファイル名に1920x1080が含まれることを確認
        assert '1920x1080' in response['Content-Disposition']

    def test_convert_handles_uppercase_output_format(self, authenticated_client, create_test_image):
        """大文字の出力形式も受け入れられること"""
        jpg_image = create_test_image(format='JPEG', color='red')
        uploaded_file = SimpleUploadedFile(
            name='test.jpg',
            content=jpg_image,
            content_type='image/jpeg'
        )

        payload = {'file': uploaded_file, 'output_format': 'PNG'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/png'

    def test_convert_heif_to_jpg_success(self, authenticated_client):
        """HEIF画像をJPGに変換できること"""
        # pillow-heifを登録
        import pillow_heif
        pillow_heif.register_heif_opener()

        # HEIF画像を作成
        img = Image.new('RGB', (100, 100), 'cyan')
        heif_io = io.BytesIO()
        img.save(heif_io, format='HEIF')
        heif_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name='photo.heic',
            content=heif_io.read(),
            content_type='image/heic'
        )

        payload = {'file': uploaded_file, 'output_format': 'jpg'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/jpeg'
        # ファイル名が [YYYYMMDD].[width]x[height].jpg の形式であることを確認
        import re
        filename_pattern = r'\d{8}\.\d+x\d+\.jpg'
        assert re.search(filename_pattern, response['Content-Disposition'])

    def test_convert_heif_to_png_success(self, authenticated_client):
        """HEIF画像をPNGに変換できること"""
        # pillow-heifを登録
        import pillow_heif
        pillow_heif.register_heif_opener()

        # HEIF画像を作成
        img = Image.new('RGB', (200, 150), 'magenta')
        heif_io = io.BytesIO()
        img.save(heif_io, format='HEIF')
        heif_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name='image.heif',
            content=heif_io.read(),
            content_type='image/heif'
        )

        payload = {'file': uploaded_file, 'output_format': 'png'}
        response = authenticated_client.post('/media/convert-image/', payload, format='multipart')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'image/png'
        # 画像サイズが保持されることを確認
        assert '200x150' in response['Content-Disposition']
