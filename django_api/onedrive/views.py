"""OneDriveアプリケーションのビュー"""
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status, authentication, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from .ms_graph_client import MSGraphClient
from .serializers import (
    FileUploadSerializer,
    CreateFolderSerializer,
    ListFilesSerializer,
    FileInfoSerializer
)


class OneDriveUploadView(APIView):
    """OneDriveへのファイルアップロードビュー"""

    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # 認証済みユーザーのみアクセス可能
    permission_classes = (permissions.IsAuthenticated,)
    # ファイルアップロード用のパーサーを設定
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        tags=['onedrive'],
        summary='ファイルアップロード',
        description='ファイルをOneDriveにアップロードします。',
        request=FileUploadSerializer,
        responses={
            201: {
                'description': 'アップロード成功',
                'content': {
                    'application/json': {
                        'example': {
                            'message': 'ファイルが正常にアップロードされました',
                            'file_info': {
                                'name': 'example.pdf',
                                'size': 1024000,
                                'created_datetime': '2024-01-01T00:00:00Z',
                                'web_url': 'https://...'
                            }
                        }
                    }
                }
            },
            400: {'description': '入力データの検証エラー'},
            401: {'description': '認証が必要です'},
            500: {'description': 'サーバーエラー'}
        }
    )
    def post(self, request, *args, **kwargs):
        """ファイルをOneDriveにアップロード"""
        serializer = FileUploadSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # バリデートされたデータを取得
        file = serializer.validated_data['file']
        folder_path = serializer.validated_data.get('folder_path', '/')
        file_name = serializer.validated_data.get('file_name') or file.name

        try:
            # MS Graphクライアントを作成
            client = MSGraphClient()

            # ファイルの内容を読み込み
            file_content = file.read()

            # OneDriveにアップロード
            result = client.upload_file_to_onedrive(
                file_content=file_content,
                file_name=file_name,
                folder_path=folder_path
            )

            # 成功レスポンスを返す
            return Response(
                {
                    'message': 'ファイルが正常にアップロードされました',
                    'file_info': FileInfoSerializer(result).data
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class OneDriveFolderView(APIView):
    """OneDriveのフォルダ操作ビュー"""

    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # 認証済みユーザーのみアクセス可能
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=['onedrive'],
        summary='フォルダ作成',
        description='OneDriveに新しいフォルダを作成します。',
        request=CreateFolderSerializer,
        responses={
            201: {
                'description': '作成成功',
                'content': {
                    'application/json': {
                        'example': {
                            'message': 'フォルダが正常に作成されました',
                            'folder_info': {
                                'name': 'New Folder',
                                'created_datetime': '2024-01-01T00:00:00Z',
                                'web_url': 'https://...'
                            }
                        }
                    }
                }
            },
            400: {'description': '入力データの検証エラー'},
            401: {'description': '認証が必要です'},
            500: {'description': 'サーバーエラー'}
        }
    )
    def post(self, request, *args, **kwargs):
        """フォルダを作成"""
        serializer = CreateFolderSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # バリデートされたデータを取得
        folder_name = serializer.validated_data['folder_name']
        parent_path = serializer.validated_data.get('parent_path', '/')

        try:
            # MS Graphクライアントを作成
            client = MSGraphClient()

            # フォルダを作成
            result = client.create_folder(
                folder_name=folder_name,
                parent_path=parent_path
            )

            # 成功レスポンスを返す
            return Response(
                {
                    'message': 'フォルダが正常に作成されました',
                    'folder_info': FileInfoSerializer(result).data
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class OneDriveListView(APIView):
    """OneDriveのファイル一覧取得ビュー"""

    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # 認証済みユーザーのみアクセス可能
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=['onedrive'],
        summary='ファイル一覧取得',
        description='指定したフォルダ内のファイル一覧を取得します。',
        parameters=[
            OpenApiParameter(
                name='folder_path',
                description='取得するフォルダのパス（デフォルト: /）',
                required=False,
                type=str,
                location=OpenApiParameter.QUERY
            )
        ],
        responses={
            200: {
                'description': '取得成功',
                'content': {
                    'application/json': {
                        'example': {
                            'folder_path': '/',
                            'count': 2,
                            'files': [
                                {
                                    'name': 'file1.pdf',
                                    'size': 1024000,
                                    'created_datetime': '2024-01-01T00:00:00Z',
                                    'web_url': 'https://...'
                                },
                                {
                                    'name': 'folder1',
                                    'folder': True,
                                    'created_datetime': '2024-01-01T00:00:00Z',
                                    'web_url': 'https://...'
                                }
                            ]
                        }
                    }
                }
            },
            400: {'description': '入力パラメータエラー'},
            401: {'description': '認証が必要です'},
            500: {'description': 'サーバーエラー'}
        }
    )
    def get(self, request, *args, **kwargs):
        """指定したフォルダ内のファイル一覧を取得"""
        serializer = ListFilesSerializer(data=request.query_params)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # バリデートされたデータを取得
        folder_path = serializer.validated_data.get('folder_path', '/')

        try:
            # MS Graphクライアントを作成
            client = MSGraphClient()

            # ファイル一覧を取得
            files = client.list_files(folder_path=folder_path)

            # シリアライズして返す
            serializer = FileInfoSerializer(files, many=True)

            return Response(
                {
                    'folder_path': folder_path,
                    'count': len(files),
                    'files': serializer.data
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )