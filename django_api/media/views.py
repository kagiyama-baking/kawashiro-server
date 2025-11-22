"""mediaアプリのビュー"""
import io
import logging
import zipfile
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from PIL import Image
from drf_spectacular.utils import extend_schema

logger = logging.getLogger(__name__)


class Zip2PdfView(APIView):
    """
    ZIPファイル内の画像をPDFに変換するビュー

    ZIPファイル内のJPEG、PNG、WEBP画像を抽出し、
    ファイル名順にソートしてPDFファイルに変換します。
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['media'],
        summary='ZIP→PDF変換',
        description='ZIPファイル内の画像（JPEG、PNG、WEBP）をPDFに変換します。'
                    '画像はファイル名順にソートされます。',
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {
                        'type': 'string',
                        'format': 'binary',
                        'description': '画像を含むZIPファイル'
                    }
                },
                'required': ['file']
            }
        },
        responses={
            200: {
                'description': '変換成功',
                'content': {
                    'application/pdf': {
                        'schema': {
                            'type': 'string',
                            'format': 'binary'
                        }
                    }
                }
            },
            400: {
                'description': 'バリデーションエラー',
                'content': {
                    'application/json': {
                        'example': {'error': 'ZIPファイル内に画像が見つかりませんでした'}
                    }
                }
            }
        }
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
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {'error': 'ファイルがアップロードされていません'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # ZIPファイルとして開く
            with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                # ZIPボム対策: ファイル数・サイズ制限
                MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
                MAX_FILES = 1000
                infos = zip_ref.infolist()

                # ファイル数チェック
                if len(infos) > MAX_FILES:
                    return Response(
                        {'error': f'ZIPファイル内のファイル数が多すぎます（最大{MAX_FILES}件まで）'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 合計ファイルサイズチェック
                total_size = sum(info.file_size for info in infos)
                if total_size > MAX_FILE_SIZE * MAX_FILES:
                    return Response(
                        {'error': 'ZIPファイル内の合計ファイルサイズが大きすぎます'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 個別ファイルサイズチェック
                for info in infos:
                    if info.file_size > MAX_FILE_SIZE:
                        return Response(
                            {'error': f'ZIPファイル内のファイルが大きすぎます（最大{MAX_FILE_SIZE // (1024*1024)}MBまで）'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # 対応する画像拡張子
                image_extensions = ('.jpg', '.jpeg', '.png', '.webp')

                # ZIP内のファイルリストを取得し、画像ファイルのみ抽出
                # パストラバーサル攻撃対策を含む
                image_files = [
                    name for name in zip_ref.namelist()
                    if (
                        name.lower().endswith(image_extensions)
                        and not name.startswith('__MACOSX/')
                        # パスセグメントに'..'が含まれないことを確認
                        and not any(part == '..' for part in name.replace('\\', '/').split('/'))
                        and not name.startswith('/')
                        and not name.startswith('\\')
                        and not name.endswith('/')
                        and name.strip() != ''
                    )
                ]

                # ファイル名順にソート
                image_files.sort()

                # 画像が見つからない場合はエラー
                if not image_files:
                    return Response(
                        {'error': 'ZIPファイル内に画像が見つかりませんでした'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 画像をPIL Imageオブジェクトに変換
                # コンテキストマネージャーを使用してメモリリークを防ぐ
                images = []
                for image_file in image_files:
                    with zip_ref.open(image_file) as img_file:
                        img_data = img_file.read()
                        with Image.open(io.BytesIO(img_data)) as img:
                            # RGBモードに変換（PDFにする際に必要）
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            # 画像をコピーしてから追加（元の画像はwith句を抜けた時点でclose）
                            images.append(img.copy())

                # PDFに変換
                pdf_buffer = io.BytesIO()
                # 最初の画像をベースにして、残りを追加
                images[0].save(
                    pdf_buffer,
                    format='PDF',
                    save_all=True,
                    append_images=images[1:] if len(images) > 1 else []
                )
                pdf_buffer.seek(0)

                # PDFファイルとしてレスポンスを返す
                response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = 'attachment; filename="converted.pdf"'
                return response

        except zipfile.BadZipFile:
            return Response(
                {'error': 'アップロードされたファイルは有効なZIPファイルではありません'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except (Image.UnidentifiedImageError, IOError) as e:
            # 画像形式エラー
            logger.warning(f'画像ファイルの形式が無効です: {str(e)}')
            return Response(
                {'error': '画像ファイルの形式が無効です'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            # ログには詳細を記録（デバッグ用）
            logger.error(f'画像の処理中にエラーが発生しました: {str(e)}', exc_info=True)
            # ユーザーには一般的なエラーメッセージのみ返す（セキュリティ対策）
            return Response(
                {'error': '画像の処理中にエラーが発生しました'},
                status=status.HTTP_400_BAD_REQUEST
            )
