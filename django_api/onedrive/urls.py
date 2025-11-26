"""OneDriveアプリケーションのURLパターン"""
from django.urls import path
from onedrive import views

# アプリケーション名の定義
app_name = 'onedrive'

# OneDrive関連のURLパターン定義
urlpatterns = [
    # ファイルアップロードエンドポイント
    path('upload/', views.OneDriveUploadView.as_view(), name='upload'),
    # フォルダ作成エンドポイント
    path('folder/', views.OneDriveFolderView.as_view(), name='create_folder'),
    # ファイル一覧取得エンドポイント
    path('list/', views.OneDriveListView.as_view(), name='list_files'),
    # ファイル削除エンドポイント
    path('delete/', views.OneDriveDeleteView.as_view(), name='delete_file'),
]