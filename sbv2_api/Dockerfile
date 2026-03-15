
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

# PyTorch (CUDA 11.8版) - style-bert-vits2はtorch<2.4が必要
RUN uv pip install "torch==2.3.1+cu118" "torchaudio==2.3.1+cu118" --index-url https://download.pytorch.org/whl/cu118

# Style-Bert-VITS2 ライブラリ（推論のみ）
# transformers>=4.42,<4.47: v4.47+はPyTorch>=2.4を要求するため、torch==2.3.1と非互換
RUN uv pip install "style-bert-vits2==2.5.0" "transformers>=4.42,<4.47"

# FastAPI関連
RUN uv pip install \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    pyyaml \
    scipy \
    "setuptools<82" \
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
