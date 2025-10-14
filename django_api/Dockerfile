FROM python:3.13-alpine                       

# リアルタイムでログを見れるように環境変数を指定
ENV PYTHONUNBUFFERD 1

# Djangoプロジェクトを置くディレクトリをコンテナ上に作成
RUN mkdir /django_api                        
WORKDIR /django_api

# uvをインストール
RUN pip install uv

# Python依存関係をインストール
COPY pyproject.toml ./
RUN uv sync --no-dev

# ローカルのdjango-apiディレクトリをコンテナにコピー
COPY . .

# アプリケーションを実行するためのユーザを作成する
RUN adduser -D django

# ユーザをrootから変更
USER django
