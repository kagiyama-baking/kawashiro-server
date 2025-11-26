"""OneDriveアプリケーションのビュー"""
import logging
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status, authentication, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from .ms_graph_client import MSGraphClient
from .exceptions import (
    ConfigurationError,
    AuthenticationError,
    UploadError,
    FolderOperationError,
    ListOperationError,
    DeleteError,
    NetworkError
)
from .serializers import (
    FileUploadSerializer,
    CreateFolderSerializer,
    ListFilesSerializer,
    DeleteFileSerializer,
    FileInfoSerializer
)

# ロガーを設定
logger = logging.getLogger(__name__)


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

        except ConfigurationError as e:
            # 設定エラーは管理者に連絡が必要
            logger.error(f"Configuration error: {str(e)}")
            return Response(
                {'error': 'サービスの設定に問題があります。管理者にお問い合わせください。'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AuthenticationError as e:
            # 認証エラー
            logger.error(f"Authentication error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの認証に失敗しました。しばらく時間をおいて再試行してください。'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except UploadError as e:
            # アップロードエラー（ユーザーに返すメッセージは具体的なエラー内容）
            logger.warning(f"Upload error: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except NetworkError as e:
            # ネットワークエラー
            logger.error(f"Network error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの接続に失敗しました。ネットワーク接続を確認して再試行してください。'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            # 予期しないエラーはログに記録し、一般的なメッセージを返す
            logger.exception("Unexpected error during file upload")
            return Response(
                {'error': 'ファイルのアップロード中に問題が発生しました。しばらく時間をおいて再試行してください。'},
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

        except ConfigurationError as e:
            # 設定エラーは管理者に連絡が必要
            logger.error(f"Configuration error: {str(e)}")
            return Response(
                {'error': 'サービスの設定に問題があります。管理者にお問い合わせください。'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AuthenticationError as e:
            # 認証エラー
            logger.error(f"Authentication error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの認証に失敗しました。しばらく時間をおいて再試行してください。'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except FolderOperationError as e:
            # フォルダ操作エラー（ユーザーに返すメッセージは具体的なエラー内容）
            logger.warning(f"Folder operation error: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except NetworkError as e:
            # ネットワークエラー
            logger.error(f"Network error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの接続に失敗しました。ネットワーク接続を確認して再試行してください。'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            # 予期しないエラーはログに記録し、一般的なメッセージを返す
            logger.exception("Unexpected error during folder creation")
            return Response(
                {'error': 'フォルダの作成中に問題が発生しました。しばらく時間をおいて再試行してください。'},
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

        except ConfigurationError as e:
            # 設定エラーは管理者に連絡が必要
            logger.error(f"Configuration error: {str(e)}")
            return Response(
                {'error': 'サービスの設定に問題があります。管理者にお問い合わせください。'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AuthenticationError as e:
            # 認証エラー
            logger.error(f"Authentication error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの認証に失敗しました。しばらく時間をおいて再試行してください。'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except ListOperationError as e:
            # ファイル一覧取得エラー（ユーザーに返すメッセージは具体的なエラー内容）
            logger.warning(f"List operation error: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except NetworkError as e:
            # ネットワークエラー
            logger.error(f"Network error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの接続に失敗しました。ネットワーク接続を確認して再試行してください。'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            # 予期しないエラーはログに記録し、一般的なメッセージを返す
            logger.exception("Unexpected error during file listing")
            return Response(
                {'error': 'ファイル一覧の取得中に問題が発生しました。しばらく時間をおいて再試行してください。'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class OneDriveDeleteView(APIView):
    """OneDriveのファイル削除ビュー"""

    # トークン認証を要求
    authentication_classes = (authentication.TokenAuthentication,)
    # 認証済みユーザーのみアクセス可能
    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        tags=['onedrive'],
        summary='ファイル削除',
        description='OneDrive上のファイルを削除します。',
        request=DeleteFileSerializer,
        responses={
            200: {
                'description': '削除成功',
                'content': {
                    'application/json': {
                        'example': {
                            'message': 'ファイルが正常に削除されました'
                        }
                    }
                }
            },
            400: {'description': '入力データの検証エラー'},
            401: {'description': '認証が必要です'},
            500: {'description': 'サーバーエラー'}
        }
    )
    def delete(self, request, *args, **kwargs):
        """ファイルを削除"""
        serializer = DeleteFileSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # バリデートされたデータを取得
        file_path = serializer.validated_data['file_path']

        try:
            # MS Graphクライアントを作成
            client = MSGraphClient()

            # ファイルを削除
            client.delete_file(file_path=file_path)

            # 成功レスポンスを返す
            return Response(
                {'message': 'ファイルが正常に削除されました'},
                status=status.HTTP_200_OK
            )

        except ConfigurationError as e:
            # 設定エラーは管理者に連絡が必要
            logger.error(f"Configuration error: {str(e)}")
            return Response(
                {'error': 'サービスの設定に問題があります。管理者にお問い合わせください。'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except AuthenticationError as e:
            # 認証エラー
            logger.error(f"Authentication error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの認証に失敗しました。しばらく時間をおいて再試行してください。'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except DeleteError as e:
            # 削除エラー（ユーザーに返すメッセージは具体的なエラー内容）
            logger.warning(f"Delete error: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except NetworkError as e:
            # ネットワークエラー
            logger.error(f"Network error: {str(e)}")
            return Response(
                {'error': 'OneDriveへの接続に失敗しました。ネットワーク接続を確認して再試行してください。'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            # 予期しないエラーはログに記録し、一般的なメッセージを返す
            logger.exception("Unexpected error during file deletion")
            return Response(
                {'error': 'ファイルの削除中に問題が発生しました。しばらく時間をおいて再試行してください。'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )