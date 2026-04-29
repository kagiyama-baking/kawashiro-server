"""mediaアプリのビュー"""

import io
import logging
import os
import re
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import quote
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from PIL import Image
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# HEIF/HEIC形式のサポートを有効化
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    # pillow-heifがインストールされていない場合はスキップ
    pass

logger = logging.getLogger(__name__)


def build_pdf_filename(uploaded_name: str | None) -> str:
    """
    アップロードファイル名から安全なPDFファイル名を生成

    パス区切り、制御文字、ダブルクォート、バックスラッシュなどHTTPヘッダ
    インジェクションに繋がりうる文字を除去した上で、拡張子を .pdf に置換する。
    """
    fallback = "converted.pdf"
    if not uploaded_name:
        return fallback
    # Windows / POSIX どちらの区切りも除去（パストラバーサル対策）
    base = os.path.basename(uploaded_name.replace("\\", "/"))
    stem = PurePosixPath(base).stem
    # 制御文字・改行・ダブルクォート・バックスラッシュを除去
    stem = re.sub(r'[\r\n"\\\x00-\x1f\x7f]', "", stem).strip()
    if not stem:
        return fallback
    return f"{stem}.pdf"


def build_attachment_disposition(filename: str) -> str:
    """
    Content-Disposition ヘッダ値を生成（RFC 6266 / RFC 5987 準拠）

    ASCII フォールバック（filename）と UTF-8 エンコード版（filename*）の
    両方を含めることで、日本語ファイル名でも対応ブラウザで正しく扱える。
    """
    ascii_fallback = (
        filename.encode("ascii", errors="replace").decode("ascii").replace("?", "_")
    )
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def is_safe_image_file(filename: str, image_extensions: tuple) -> bool:
    """
    ファイル名が安全な画像ファイルかどうかを判定

    Args:
        filename: チェックするファイル名
        image_extensions: 許可する画像拡張子のタプル

    Returns:
        bool: 安全な画像ファイルの場合True
    """
    return (
        filename.lower().endswith(image_extensions)
        and not filename.startswith("__MACOSX/")
        # パスセグメントに'..'が含まれないことを確認
        and not any(part == ".." for part in filename.replace("\\", "/").split("/"))
        and not filename.startswith("/")
        and not filename.startswith("\\")
        and not filename.endswith("/")
        and filename.strip() != ""
    )


class ZipToPdfView(APIView):
    """
    ZIPファイル内の画像をPDFに変換するビュー

    ZIPファイル内のJPEG、PNG、WEBP画像を抽出し、
    ファイル名順にソートしてPDFファイルに変換します。
    """

    permission_classes = [IsAuthenticated]

    # ZIPボム対策の制限値
    MAX_TOTAL_SIZE = 1 * 1024 * 1024 * 1024  # 1GB（展開後の合計サイズ）
    MAX_FILES = 1000

    # 対応する画像拡張子
    IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

    @extend_schema(
        tags=["media"],
        summary="ZIP→PDF変換",
        description="ZIPファイル内の画像（JPEG、PNG、WEBP）をPDFに変換します。"
        "画像はファイル名順にソートされます。",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": "画像を含むZIPファイル",
                    }
                },
                "required": ["file"],
            }
        },
        responses={
            200: {
                "description": "変換成功",
                "content": {
                    "application/pdf": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                },
            },
            400: {
                "description": "バリデーションエラー",
                "content": {
                    "application/json": {
                        "example": {
                            "error": "ZIPファイル内に画像が見つかりませんでした"
                        }
                    }
                },
            },
        },
    )
    def post(self, request):
        """
        ZIPファイルをアップロードしてPDFに変換

        Args:
            request: HTTPリクエストオブジェクト（fileフィールドにZIPファイルを含む）

        Returns:
            HttpResponse: PDFファイル、またはエラーレスポンス
        """
        # ファイルの存在確認
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"error": "ファイルがアップロードされていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # ZIPファイルとして開く
            with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
                # ZIPボム対策: ファイル数・サイズ制限
                infos = zip_ref.infolist()

                # ファイル数チェック
                if len(infos) > self.MAX_FILES:
                    return Response(
                        {
                            "error": f"ZIPファイル内のファイル数が多すぎます（最大{self.MAX_FILES}件まで）"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # 合計ファイルサイズチェック（ZIPボム対策）
                total_size = sum(info.file_size for info in infos)
                if total_size > self.MAX_TOTAL_SIZE:
                    return Response(
                        {
                            "error": f"ZIPファイル内の合計ファイルサイズが大きすぎます（最大{self.MAX_TOTAL_SIZE // (1024 * 1024 * 1024)}GBまで）"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # ZIP内のファイルリストを取得し、画像ファイルのみ抽出
                # パストラバーサル攻撃対策を含む
                image_files = [
                    name
                    for name in zip_ref.namelist()
                    if is_safe_image_file(name, self.IMAGE_EXTENSIONS)
                ]

                # ファイル名順にソート
                image_files.sort()

                # 画像が見つからない場合はエラー
                if not image_files:
                    return Response(
                        {"error": "ZIPファイル内に画像が見つかりませんでした"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # 画像をPIL Imageオブジェクトに変換
                # コンテキストマネージャーを使用してメモリリークを防ぐ
                images = []
                for image_file in image_files:
                    with zip_ref.open(image_file) as img_file:
                        img_data = img_file.read()
                        with Image.open(io.BytesIO(img_data)) as img:
                            # RGBモードに変換（PDFにする際に必要）
                            if img.mode != "RGB":
                                img = img.convert("RGB")
                            # 画像をコピーしてから追加（元の画像はwith句を抜けた時点でclose）
                            images.append(img.copy())

                # PDFに変換
                pdf_buffer = io.BytesIO()
                # 最初の画像をベースにして、残りを追加
                images[0].save(
                    pdf_buffer,
                    format="PDF",
                    save_all=True,
                    append_images=images[1:] if len(images) > 1 else [],
                )
                pdf_buffer.seek(0)

                # PDFファイルとしてレスポンスを返す
                response = HttpResponse(
                    pdf_buffer.getvalue(), content_type="application/pdf"
                )
                pdf_filename = build_pdf_filename(uploaded_file.name)
                response["Content-Disposition"] = build_attachment_disposition(
                    pdf_filename
                )
                return response

        except zipfile.BadZipFile:
            return Response(
                {
                    "error": "アップロードされたファイルは有効なZIPファイルではありません"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (OSError, Image.UnidentifiedImageError) as e:
            # 画像形式エラー
            logger.warning(f"画像ファイルの形式が無効です: {str(e)}")
            return Response(
                {"error": "画像ファイルの形式が無効です"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # ログには詳細を記録（デバッグ用）
            logger.error(f"画像の処理中にエラーが発生しました: {str(e)}", exc_info=True)
            # ユーザーには一般的なエラーメッセージのみ返す（セキュリティ対策）
            return Response(
                {"error": "画像の処理中にエラーが発生しました"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ImageConvertView(APIView):
    """
    画像形式を変換するビュー

    入力形式: jpg / png / webp / tiff / heif / heic / psd / dng
    出力形式: jpg / png / webp / tiff
    変換後のファイル名は [YYYYMMDD].[width]x[height].[extension] の形式になります。
    """

    permission_classes = [IsAuthenticated]

    # サポートする入出力形式
    SUPPORTED_FORMATS = {
        "jpg": {"mime": "image/jpeg", "pil_format": "JPEG", "ext": "jpg"},
        "png": {"mime": "image/png", "pil_format": "PNG", "ext": "png"},
        "webp": {"mime": "image/webp", "pil_format": "WEBP", "ext": "webp"},
        "tiff": {"mime": "image/tiff", "pil_format": "TIFF", "ext": "tiff"},
    }

    # ファイルサイズ制限（50MB）
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

    # JPEG品質パラメータのデフォルト値と範囲
    DEFAULT_JPEG_QUALITY = 85
    MIN_JPEG_QUALITY = 1
    MAX_JPEG_QUALITY = 100

    @extend_schema(
        tags=["media"],
        summary="画像形式変換",
        description="画像形式を変換します。\n\n"
        "入力形式: jpg / png / webp / tiff / heif / heic / psd / dng\n"
        "出力形式: jpg / png / webp / tiff\n\n"
        "出力ファイル名は [YYYYMMDD].[width]x[height].[extension] の形式になります。\n\n"
        "JPEG形式で出力する場合、quality パラメータで品質を指定できます（1-100、デフォルト: 85）。",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": "変換する画像ファイル",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["jpg", "png", "webp", "tiff"],
                        "description": "出力形式",
                    },
                    "quality": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "JPEG品質（1-100、デフォルト: 85）。JPEG以外の形式では無視されます。",
                    },
                },
                "required": ["file", "output_format"],
            }
        },
        responses={
            200: {
                "description": "変換成功",
                "content": {
                    "image/*": {"schema": {"type": "string", "format": "binary"}}
                },
            },
            400: {
                "description": "バリデーションエラー",
                "content": {
                    "application/json": {
                        "example": {"error": "サポートされていない出力形式です"}
                    }
                },
            },
        },
    )
    def post(self, request):
        """
        画像形式を変換

        Args:
            request: HTTPリクエストオブジェクト（fileフィールドに画像ファイル、
                    output_formatフィールドに出力形式を含む）

        Returns:
            HttpResponse: 変換された画像ファイル、またはエラーレスポンス
        """
        # ファイルの存在確認
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"error": "ファイルがアップロードされていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ファイルサイズチェック（DoS対策）
        if uploaded_file.size > self.MAX_FILE_SIZE:
            return Response(
                {
                    "error": f"ファイルサイズが大きすぎます（最大{self.MAX_FILE_SIZE // (1024 * 1024)}MBまで）"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 出力形式の確認
        output_format = request.data.get("output_format", "").lower()
        if not output_format:
            return Response(
                {"error": "出力形式が指定されていません"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if output_format not in self.SUPPORTED_FORMATS:
            return Response(
                {"error": "サポートされていない出力形式です"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # JPEG品質パラメータの取得とバリデーション
        quality = self.DEFAULT_JPEG_QUALITY
        if output_format == "jpg" and "quality" in request.data:
            try:
                quality = int(request.data["quality"])
                if quality < self.MIN_JPEG_QUALITY or quality > self.MAX_JPEG_QUALITY:
                    return Response(
                        {
                            "error": f"品質パラメータは{self.MIN_JPEG_QUALITY}から{self.MAX_JPEG_QUALITY}の範囲で指定してください"
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except (ValueError, TypeError):
                return Response(
                    {"error": "品質パラメータは整数で指定してください"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            # 画像を開く
            with Image.open(uploaded_file) as img:
                # 画像の作成日を取得
                creation_date = self._get_creation_date(img)

                # 画像サイズを取得
                width, height = img.size

                # ファイル名を生成: YYYYMMDD.widthxheight.extension
                filename = f"{creation_date}.{width}x{height}.{self.SUPPORTED_FORMATS[output_format]['ext']}"

                # RGBモードに変換（JPEGやその他の形式で必要）
                # 変換後の画像を別変数に格納してリソースリークを防ぐ
                converted_img = img
                if output_format == "jpg":
                    if img.mode in ("RGBA", "LA"):
                        # アルファチャンネルがある場合は白背景で合成
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        converted_img = background
                    elif img.mode == "P":
                        # パレットモードの場合、透明度情報を確認
                        if "transparency" in img.info:
                            # 透明度がある場合はRGBAに変換してから白背景で合成
                            tmp_img = img.convert("RGBA")
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(tmp_img, mask=tmp_img.split()[-1])
                            converted_img = background
                        else:
                            # 透明度がない場合は直接RGBに変換
                            converted_img = img.convert("RGB")
                    elif img.mode != "RGB":
                        converted_img = img.convert("RGB")

                # 画像を変換
                img_buffer = io.BytesIO()
                # JPEG形式の場合は品質パラメータを指定
                if output_format == "jpg":
                    converted_img.save(
                        img_buffer,
                        format=self.SUPPORTED_FORMATS[output_format]["pil_format"],
                        quality=quality,
                    )
                else:
                    converted_img.save(
                        img_buffer,
                        format=self.SUPPORTED_FORMATS[output_format]["pil_format"],
                    )
                img_buffer.seek(0)

                # レスポンスを返す
                response = HttpResponse(
                    img_buffer.getvalue(),
                    content_type=self.SUPPORTED_FORMATS[output_format]["mime"],
                )
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                return response

        except (OSError, Image.UnidentifiedImageError) as e:
            # 画像形式エラー
            logger.warning(f"画像ファイルの形式が無効です: {str(e)}")
            return Response(
                {"error": "画像ファイルの形式が無効です"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            # ログには詳細を記録（デバッグ用）
            logger.error(f"画像の処理中にエラーが発生しました: {str(e)}", exc_info=True)
            # ユーザーには一般的なエラーメッセージのみ返す（セキュリティ対策）
            return Response(
                {"error": "画像の処理中にエラーが発生しました"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def _get_creation_date(self, img: Image.Image) -> str:
        """
        画像の作成日を取得

        Args:
            img: PIL Imageオブジェクト

        Returns:
            str: YYYYMMDD形式の日付文字列
        """
        try:
            # EXIFデータから撮影日時を取得
            exif_data = img.getexif()
            if exif_data:
                # DateTimeOriginal (36867) または DateTime (306) を探す
                for tag_id in [36867, 306]:
                    if tag_id in exif_data:
                        date_str = exif_data[tag_id]
                        # EXIF日時フォーマット: "YYYY:MM:DD HH:MM:SS"
                        date_obj = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                        return date_obj.strftime("%Y%m%d")
        except (ValueError, KeyError, AttributeError):
            # EXIFデータの取得・解析に失敗した場合は無視
            # ValueError: 日時フォーマットが不正
            # KeyError: EXIFタグが存在しない
            # AttributeError: EXIFデータが不正
            pass

        # EXIFデータがない場合は現在日時を使用（Django設定のタイムゾーンを適用）
        timezone = ZoneInfo(settings.TIME_ZONE)
        now = datetime.now(timezone)
        return now.strftime("%Y%m%d")
