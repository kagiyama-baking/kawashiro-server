"""mediaアプリのビュー"""
import io
import zipfile
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from PIL import Image
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes


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
                # 対応する画像拡張子
                image_extensions = ('.jpg', '.jpeg', '.png', '.webp')

                # ZIP内のファイルリストを取得し、画像ファイルのみ抽出
                image_files = [
                    name for name in zip_ref.namelist()
                    if name.lower().endswith(image_extensions) and not name.startswith('__MACOSX/')
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
                images = []
                for image_file in image_files:
                    with zip_ref.open(image_file) as img_file:
                        # 画像を読み込み
                        img_data = img_file.read()
                        img = Image.open(io.BytesIO(img_data))

                        # RGBモードに変換（PDFにする際に必要）
                        if img.mode != 'RGB':
                            img = img.convert('RGB')

                        images.append(img)

                # PDFに変換
                pdf_buffer = io.BytesIO()
                if len(images) > 0:
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
        except Exception as e:
            return Response(
                {'error': f'画像の処理中にエラーが発生しました: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
