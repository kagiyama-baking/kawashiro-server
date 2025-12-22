
FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=Asia/Tokyo

# 必要パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ffmpeg \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv のインストール
RUN pip install --no-cache-dir uv

WORKDIR /app

# Python仮想環境をuvで構築
RUN uv venv /app/venv --python 3.10
ENV PATH="/app/venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/venv"

# PyTorch (CPU版)
RUN uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Style-Bert-VITS2 ライブラリ（推論のみ）
RUN uv pip install style-bert-vits2

# FastAPI関連
RUN uv pip install \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    pyyaml \
    scipy \
    setuptools \
    "numpy<2"

# BERTモデルの事前ダウンロード（起動時間短縮）
# huggingface_hubを使って日本語BERTモデルをダウンロード
RUN python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('ku-nlp/deberta-v2-large-japanese-char-wwm', local_dir='/app/bert/deberta-v2-large-japanese-char-wwm')"

# Style-BERT-VITS2のデフォルトパスを設定
ENV DEFAULT_BERT_TOKENIZER_PATH="/app/bert/deberta-v2-large-japanese-char-wwm"

# アプリケーションファイルをコピー
COPY server.py /app/server.py
COPY config.yml /app/config.yml

# モデル格納ディレクトリ作成
RUN mkdir -p /app/model_assets

# 非rootユーザーで実行
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5000"]
