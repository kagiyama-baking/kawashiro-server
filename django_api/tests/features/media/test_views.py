"""mediaアプリのビューテスト"""

import io
import re
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status

pytestmark = pytest.mark.django_db


@pytest.fixture
def create_test_image():
    """テスト用の画像を作成するヘルパー関数"""

    def _create_image(format="JPEG", size=(100, 100), color="red"):
        """
        指定された形式とサイズの画像を作成

        Args:
            format: 画像フォーマット（'JPEG', 'PNG', 'WEBP'）
            size: 画像サイズ（幅, 高さ）
            color: 画像の色

        Returns:
            bytes: 画像データ
        """
        img = Image.new("RGB", size, color)
        img_io = io.BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return img_io.read()

    return _create_image


@pytest.fixture(scope="module")
def setup_heif_support():
    """HEIF/HEIC形式のサポートを有効化（モジュールレベルで1回のみ実行）"""
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        # pillow-heifがインストールされていない場合はスキップ
        pytest.skip("pillow-heif is not installed")


@pytest.fixture
def create_zip_file(create_test_image):
    """テスト用のZIPファイルを作成するヘルパー関数"""

    def _create_zip(files, zip_name="test.zip"):
        """
        ファイルを含むZIPファイルを作成

        Args:
            files: ファイルのリスト [{'name': 'file.jpg', 'format': 'JPEG', 'color': 'red'}, ...]
                   または [{'name': 'file.txt', 'content': b'text content'}, ...]
            zip_name: アップロードファイル名（デフォルト: "test.zip"）

        Returns:
            SimpleUploadedFile: ZIPファイルオブジェクト
        """
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_info in files:
                if "format" in file_info:
                    # 画像ファイル
                    content = create_test_image(
                        format=file_info.get("format", "JPEG"),
                        color=file_info.get("color", "red"),
                    )
                else:
                    # 通常のファイル
                    content = file_info.get("content", b"test content")
                zip_file.writestr(file_info["name"], content)

        zip_io.seek(0)
        return SimpleUploadedFile(
            name=zip_name, content=zip_io.read(), content_type="application/zip"
        )

    return _create_zip


@pytest.mark.api
class TestZipToPdfView:
    """ZipToPdfViewのテストクラス"""

    def test_convert_zip_to_pdf_success(self, authenticated_client, create_zip_file):
        """画像を含むZIPファイルを正常にPDFに変換できること"""
        # 3つの画像ファイルを含むZIPを作成（ファイル名順を確認するため）
        zip_file = create_zip_file(
            [
                {"name": "03_image.jpg", "format": "JPEG", "color": "blue"},
                {"name": "01_image.png", "format": "PNG", "color": "red"},
                {"name": "02_image.webp", "format": "WEBP", "color": "green"},
            ]
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert "Content-Disposition" in response
        assert "attachment" in response["Content-Disposition"]
        assert response.content.startswith(b"%PDF")

    def test_convert_zip_with_mixed_files(self, authenticated_client, create_zip_file):
        """画像ファイルとその他のファイルが混在する場合、画像のみ処理されること"""
        zip_file = create_zip_file(
            [
                {"name": "image1.jpg", "format": "JPEG", "color": "red"},
                {"name": "readme.txt", "content": b"This is a readme file"},
                {"name": "image2.png", "format": "PNG", "color": "blue"},
                {"name": "data.json", "content": b'{"key": "value"}'},
            ]
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_convert_zip_without_images_fails(
        self, authenticated_client, create_zip_file
    ):
        """画像が含まれないZIPファイルの場合はエラーになること"""
        zip_file = create_zip_file(
            [
                {"name": "readme.txt", "content": b"This is a readme file"},
                {"name": "data.json", "content": b'{"key": "value"}'},
            ]
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert "画像" in response.data["error"]

    def test_convert_zip_to_pdf_without_authentication_fails(
        self, api_client, create_zip_file
    ):
        """認証なしでZIP→PDF変換が失敗すること"""
        zip_file = create_zip_file(
            [
                {"name": "image.jpg", "format": "JPEG", "color": "red"},
            ]
        )

        payload = {"file": zip_file}
        response = api_client.post("/media/zip-to-pdf/", payload, format="multipart")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_convert_zip_to_pdf_without_file_fails(self, authenticated_client):
        """ファイルなしでリクエストした場合はエラーになること"""
        response = authenticated_client.post(
            "/media/zip-to-pdf/", {}, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_convert_non_zip_file_fails(self, authenticated_client, mock_file):
        """ZIP以外のファイルをアップロードした場合はエラーになること"""
        payload = {"file": mock_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_convert_sorted_images_to_pdf(self, authenticated_client, create_zip_file):
        """ファイル名が異なる順序の画像を含むZIPをPDFに変換できること"""
        # ファイル名が辞書順になるようにZIPを作成
        zip_file = create_zip_file(
            [
                {"name": "z_last.jpg", "format": "JPEG", "color": "blue"},
                {"name": "a_first.jpg", "format": "JPEG", "color": "red"},
                {"name": "m_middle.jpg", "format": "JPEG", "color": "green"},
            ]
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"
        # 実装では、ファイル名順にソートされる
        # （PDFの内容を解析するのは複雑なので、ステータスコードのみで確認）

    def test_supported_image_formats(self, authenticated_client, create_zip_file):
        """JPEG、PNG、WEBP形式の画像がすべてサポートされること"""
        zip_file = create_zip_file(
            [
                {"name": "image.jpg", "format": "JPEG", "color": "red"},
                {"name": "image.jpeg", "format": "JPEG", "color": "green"},
                {"name": "image.png", "format": "PNG", "color": "blue"},
                {"name": "image.webp", "format": "WEBP", "color": "yellow"},
            ]
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/pdf"

    def test_pdf_filename_matches_uploaded_zip(
        self, authenticated_client, create_zip_file
    ):
        """変換後のPDFファイル名がアップロードされたZIPの名前（拡張子.pdf）になること"""
        zip_file = create_zip_file(
            [{"name": "image.jpg", "format": "JPEG", "color": "red"}],
            zip_name="aaa.zip",
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert 'filename="aaa.pdf"' in response["Content-Disposition"]

    def test_pdf_filename_preserves_inner_dots(
        self, authenticated_client, create_zip_file
    ):
        """ドットを複数含むZIP名は最後の拡張子のみ.pdfに置換されること"""
        zip_file = create_zip_file(
            [{"name": "image.jpg", "format": "JPEG", "color": "red"}],
            zip_name="my.archive.v2.zip",
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert 'filename="my.archive.v2.pdf"' in response["Content-Disposition"]

    def test_pdf_filename_with_japanese_uses_rfc5987(
        self, authenticated_client, create_zip_file
    ):
        """日本語ZIP名の場合、RFC 5987形式（filename*=UTF-8''...）が含まれること"""
        zip_file = create_zip_file(
            [{"name": "image.jpg", "format": "JPEG", "color": "red"}],
            zip_name="あいうえお.zip",
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        disposition = response["Content-Disposition"]
        # RFC 5987 形式のパーセントエンコードされたファイル名
        assert "filename*=UTF-8''" in disposition
        assert "%E3%81%82%E3%81%84%E3%81%86%E3%81%88%E3%81%8A.pdf" in disposition

    def test_pdf_filename_preserves_spaces_and_symbols(
        self, authenticated_client, create_zip_file
    ):
        """半角スペース・括弧・ハイフン等の記号を含むZIP名がそのまま保持されること"""
        zip_file = create_zip_file(
            [{"name": "image.jpg", "format": "JPEG", "color": "red"}],
            zip_name="my-file_v2 (final) [draft].zip",
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        disposition = response["Content-Disposition"]
        # ASCIIフォールバックには元の文字（スペース・括弧含む）がそのまま入る
        assert 'filename="my-file_v2 (final) [draft].pdf"' in disposition
        # RFC 5987 はパーセントエンコード済み
        assert (
            "my-file_v2%20%28final%29%20%5Bdraft%5D.pdf" in disposition
        )

    def test_pdf_filename_strips_path_traversal(
        self, authenticated_client, create_zip_file
    ):
        """ZIP名にパス区切りが含まれてもbasenameのみが使われること"""
        zip_file = create_zip_file(
            [{"name": "image.jpg", "format": "JPEG", "color": "red"}],
            zip_name="../../etc/passwd.zip",
        )

        payload = {"file": zip_file}
        response = authenticated_client.post(
            "/media/zip-to-pdf/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        disposition = response["Content-Disposition"]
        assert 'filename="passwd.pdf"' in disposition
        # パス成分が漏れていないこと
        assert ".." not in disposition
        assert "/" not in disposition.split("filename=", 1)[1].split(";", 1)[0]


@pytest.mark.api
class TestImageConvertView:
    """ImageConvertViewのテストクラス"""

    def test_convert_jpg_to_png_success(self, authenticated_client, create_test_image):
        """JPG画像をPNGに変換できること"""
        jpg_image = create_test_image(format="JPEG", color="red")
        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=jpg_image, content_type="image/jpeg"
        )

        payload = {"file": uploaded_file, "output_format": "png"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"
        assert "Content-Disposition" in response
        assert "attachment" in response["Content-Disposition"]
        # ファイル名が [YYYYMMDD].[width]x[height].png の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.png"
        assert re.search(filename_pattern, response["Content-Disposition"])
        # PNG画像のシグネチャを確認
        assert response.content.startswith(b"\x89PNG")

    def test_convert_png_to_jpg_success(self, authenticated_client, create_test_image):
        """PNG画像をJPGに変換できること"""
        png_image = create_test_image(format="PNG", color="blue")
        uploaded_file = SimpleUploadedFile(
            name="test.png", content=png_image, content_type="image/png"
        )

        payload = {"file": uploaded_file, "output_format": "jpg"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/jpeg"
        # ファイル名が [YYYYMMDD].[width]x[height].jpg の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.jpg"
        assert re.search(filename_pattern, response["Content-Disposition"])
        # JPEG画像のシグネチャを確認
        assert response.content.startswith(b"\xff\xd8\xff")

    def test_convert_jpg_to_webp_success(self, authenticated_client, create_test_image):
        """JPG画像をWebPに変換できること"""
        jpg_image = create_test_image(format="JPEG", color="green")
        uploaded_file = SimpleUploadedFile(
            name="image.jpg", content=jpg_image, content_type="image/jpeg"
        )

        payload = {"file": uploaded_file, "output_format": "webp"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/webp"
        # ファイル名が [YYYYMMDD].[width]x[height].webp の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.webp"
        assert re.search(filename_pattern, response["Content-Disposition"])
        # WebP画像のシグネチャを確認
        assert b"WEBP" in response.content[:20]

    def test_convert_png_to_tiff_success(self, authenticated_client, create_test_image):
        """PNG画像をTIFFに変換できること"""
        png_image = create_test_image(format="PNG", color="yellow")
        uploaded_file = SimpleUploadedFile(
            name="photo.png", content=png_image, content_type="image/png"
        )

        payload = {"file": uploaded_file, "output_format": "tiff"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/tiff"
        # ファイル名が [YYYYMMDD].[width]x[height].tiff の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.tiff"
        assert re.search(filename_pattern, response["Content-Disposition"])
        # TIFF画像のシグネチャを確認（リトルエンディアン or ビッグエンディアン）
        assert response.content.startswith((b"II\x2a\x00", b"MM\x00\x2a"))

    def test_convert_webp_to_jpg_success(self, authenticated_client, create_test_image):
        """WebP画像をJPGに変換できること"""
        webp_image = create_test_image(format="WEBP", color="purple")
        uploaded_file = SimpleUploadedFile(
            name="sample.webp", content=webp_image, content_type="image/webp"
        )

        payload = {"file": uploaded_file, "output_format": "jpg"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/jpeg"
        # ファイル名が [YYYYMMDD].[width]x[height].jpg の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.jpg"
        assert re.search(filename_pattern, response["Content-Disposition"])

    def test_convert_tiff_to_png_success(self, authenticated_client):
        """TIFF画像をPNGに変換できること"""
        # TIFFファイルを作成
        tiff_img = Image.new("RGB", (100, 100), "orange")
        tiff_io = io.BytesIO()
        tiff_img.save(tiff_io, format="TIFF")
        tiff_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="document.tiff", content=tiff_io.read(), content_type="image/tiff"
        )

        payload = {"file": uploaded_file, "output_format": "png"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"
        # ファイル名が [YYYYMMDD].[width]x[height].png の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.png"
        assert re.search(filename_pattern, response["Content-Disposition"])

    def test_convert_without_file_fails(self, authenticated_client):
        """ファイルなしでリクエストした場合はエラーになること"""
        payload = {"output_format": "png"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_convert_without_output_format_fails(
        self, authenticated_client, create_test_image
    ):
        """出力形式を指定しない場合はエラーになること"""
        jpg_image = create_test_image(format="JPEG", color="red")
        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=jpg_image, content_type="image/jpeg"
        )

        payload = {"file": uploaded_file}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_convert_with_invalid_output_format_fails(
        self, authenticated_client, create_test_image
    ):
        """サポートされていない出力形式を指定した場合はエラーになること"""
        jpg_image = create_test_image(format="JPEG", color="red")
        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=jpg_image, content_type="image/jpeg"
        )

        payload = {"file": uploaded_file, "output_format": "bmp"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert "サポートされていない" in response.data["error"]

    def test_convert_invalid_image_file_fails(self, authenticated_client, mock_file):
        """無効な画像ファイルの場合はエラーになること"""
        payload = {"file": mock_file, "output_format": "png"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_convert_without_authentication_fails(self, api_client, create_test_image):
        """認証なしで画像変換が失敗すること"""
        jpg_image = create_test_image(format="JPEG", color="red")
        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=jpg_image, content_type="image/jpeg"
        )

        payload = {"file": uploaded_file, "output_format": "png"}
        response = api_client.post("/media/convert-image/", payload, format="multipart")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_convert_filename_format_with_dimensions(
        self, authenticated_client, create_test_image
    ):
        """変換後のファイル名が画像サイズを含むこと"""
        # 特定のサイズの画像を作成
        img = Image.new("RGB", (1920, 1080), "red")
        img_io = io.BytesIO()
        img.save(img_io, format="JPEG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=img_io.read(), content_type="image/jpeg"
        )

        payload = {"file": uploaded_file, "output_format": "png"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        # ファイル名に1920x1080が含まれることを確認
        assert "1920x1080" in response["Content-Disposition"]

    def test_convert_handles_uppercase_output_format(
        self, authenticated_client, create_test_image
    ):
        """大文字の出力形式も受け入れられること"""
        jpg_image = create_test_image(format="JPEG", color="red")
        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=jpg_image, content_type="image/jpeg"
        )

        payload = {"file": uploaded_file, "output_format": "PNG"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"

    def test_convert_heif_to_jpg_success(
        self, authenticated_client, setup_heif_support
    ):
        """HEIF画像をJPGに変換できること"""
        # HEIF画像を作成
        img = Image.new("RGB", (100, 100), "cyan")
        heif_io = io.BytesIO()
        img.save(heif_io, format="HEIF")
        heif_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="photo.heic", content=heif_io.read(), content_type="image/heic"
        )

        payload = {"file": uploaded_file, "output_format": "jpg"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/jpeg"
        # ファイル名が [YYYYMMDD].[width]x[height].jpg の形式であることを確認
        filename_pattern = r"\d{8}\.\d+x\d+\.jpg"
        assert re.search(filename_pattern, response["Content-Disposition"])

    def test_convert_heif_to_png_success(
        self, authenticated_client, setup_heif_support
    ):
        """HEIF画像をPNGに変換できること"""
        # HEIF画像を作成
        img = Image.new("RGB", (200, 150), "magenta")
        heif_io = io.BytesIO()
        img.save(heif_io, format="HEIF")
        heif_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="image.heif", content=heif_io.read(), content_type="image/heif"
        )

        payload = {"file": uploaded_file, "output_format": "png"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"
        # 画像サイズが保持されることを確認
        assert "200x150" in response["Content-Disposition"]

    def test_convert_palette_image_to_jpg_success(self, authenticated_client):
        """パレットモード画像をJPGに変換できること"""
        # パレットモード画像を作成
        img = Image.new("P", (100, 100), 128)
        img_io = io.BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="palette.png", content=img_io.read(), content_type="image/png"
        )

        payload = {"file": uploaded_file, "output_format": "jpg"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/jpeg"
        assert "100x100" in response["Content-Disposition"]

    def test_convert_file_size_limit_exceeded(self, authenticated_client):
        """50MBを超えるファイルはエラーになること"""
        # 51MBのダミーデータを作成（実際の画像ではなく、サイズチェックのみのテスト）
        large_data = b"0" * (51 * 1024 * 1024)  # 51MB

        uploaded_file = SimpleUploadedFile(
            name="large.dng", content=large_data, content_type="image/x-adobe-dng"
        )

        payload = {"file": uploaded_file, "output_format": "jpg"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert "ファイルサイズ" in response.data["error"]

    def test_convert_jpeg_quality_parameter(self, authenticated_client):
        """JPEG変換時に品質パラメータが適用されること"""
        # PNG画像を作成
        img = Image.new("RGB", (100, 100), "yellow")
        img_io = io.BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="test.png", content=img_io.read(), content_type="image/png"
        )

        payload = {"file": uploaded_file, "output_format": "jpg"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/jpeg"
        # 品質が適用された結果、ファイルサイズが妥当であることを確認
        assert len(response.content) > 0

    def test_convert_jpeg_with_custom_quality(self, authenticated_client):
        """JPEG変換時にカスタム品質パラメータを指定できること"""
        # PNG画像を作成
        img = Image.new("RGB", (200, 200), "blue")
        img_io = io.BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="test.png", content=img_io.read(), content_type="image/png"
        )

        # 高品質で変換
        payload_high = {"file": uploaded_file, "output_format": "jpg", "quality": "95"}
        response_high = authenticated_client.post(
            "/media/convert-image/", payload_high, format="multipart"
        )

        # 新しいファイルを作成（同じ内容）
        img_io.seek(0)
        uploaded_file2 = SimpleUploadedFile(
            name="test2.png", content=img_io.read(), content_type="image/png"
        )

        # 低品質で変換
        payload_low = {"file": uploaded_file2, "output_format": "jpg", "quality": "50"}
        response_low = authenticated_client.post(
            "/media/convert-image/", payload_low, format="multipart"
        )

        assert response_high.status_code == status.HTTP_200_OK
        assert response_low.status_code == status.HTTP_200_OK
        # 高品質の方がファイルサイズが大きいことを確認
        assert len(response_high.content) > len(response_low.content)

    def test_convert_jpeg_quality_out_of_range(self, authenticated_client):
        """JPEG品質パラメータが範囲外の場合はエラーになること"""
        img = Image.new("RGB", (100, 100), "red")
        img_io = io.BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="test.png", content=img_io.read(), content_type="image/png"
        )

        # 範囲外の品質（101）
        payload = {"file": uploaded_file, "output_format": "jpg", "quality": "101"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert "品質" in response.data["error"]

    def test_convert_jpeg_quality_non_numeric(self, authenticated_client):
        """JPEG品質パラメータが数値でない場合はエラーになること"""
        img = Image.new("RGB", (100, 100), "green")
        img_io = io.BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="test.png", content=img_io.read(), content_type="image/png"
        )

        # 数値でない品質
        payload = {"file": uploaded_file, "output_format": "jpg", "quality": "high"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data
        assert "品質" in response.data["error"]

    def test_convert_png_ignores_quality_parameter(self, authenticated_client):
        """PNG変換時は品質パラメータを無視すること"""
        img = Image.new("RGB", (100, 100), "purple")
        img_io = io.BytesIO()
        img.save(img_io, format="JPEG")
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            name="test.jpg", content=img_io.read(), content_type="image/jpeg"
        )

        # PNGに変換する際にqualityパラメータを指定
        payload = {"file": uploaded_file, "output_format": "png", "quality": "50"}
        response = authenticated_client.post(
            "/media/convert-image/", payload, format="multipart"
        )

        # エラーにならず、正常に変換されること
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "image/png"
