"""
Style-BERT-VITS2 読み上げAPIサーバー
Kawashiro Server 内部サービス用
"""

import io
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import scipy.io.wavfile as wavfile
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from style_bert_vits2.constants import Languages
from style_bert_vits2.nlp import bert_models
from style_bert_vits2.tts_model import TTSModel

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# 設定
CONFIG_PATH = Path("/app/config.yml")
MODEL_ASSETS_PATH = Path("/app/model_assets")
BERT_MODEL_PATH = Path("/app/bert/deberta-v2-large-japanese-char-wwm")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


config = load_config()

# 設定値を取得
MAX_TEXT_LENGTH = config.get("max_length", 500)

# 出力フォーマット設定
FORMAT_MEDIA_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
}

# FastAPIアプリ（内部サービスのためCORS不要）
app = FastAPI(
    title="Style-BERT-VITS2 TTS API",
    description="Kawashiro Server 内部TTSサービス",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """起動時にBERTモデルをロード"""
    logger.info("Loading BERT models...")
    bert_model = bert_models.load_model(Languages.JP, pretrained_model_name_or_path=str(BERT_MODEL_PATH))
    bert_models.load_tokenizer(Languages.JP, pretrained_model_name_or_path=str(BERT_MODEL_PATH))
    # BERTモデルをfloat32に変換（CPU環境対応）
    if bert_model is not None:
        bert_model.float()
        logger.info("Converted BERT model to float32")
    logger.info("BERT models loaded")

    # TTSモデルのプリロード（初回リクエストのレイテンシを排除）
    models = list_available_models()
    logger.info("Available TTS models: %s", models)
    for model_name in models:
        logger.info("Preloading TTS model: %s", model_name)
        try:
            get_model(model_name)
        except Exception as e:
            logger.warning("Failed to preload model %s: %s", model_name, e)
    logger.info(
        "TTS model preloading complete: %d/%d models loaded",
        len(_models), len(models),
    )


# モデルキャッシュ
_models: dict[str, TTSModel] = {}


def list_available_models() -> list[str]:
    """利用可能なモデル一覧"""
    models = []
    if MODEL_ASSETS_PATH.exists():
        for p in MODEL_ASSETS_PATH.iterdir():
            if p.is_dir() and (p / "config.json").exists():
                models.append(p.name)
    return sorted(models)


def get_model(model_name: str) -> TTSModel:
    """TTSモデルを取得（キャッシュあり）"""
    # パストラバーサル防止: 英数字・ハイフン・アンダースコアのみ許可
    if not re.match(r"^[a-zA-Z0-9_\-]+$", model_name):
        raise HTTPException(status_code=400, detail="Invalid model name")

    if model_name not in _models:
        model_path = MODEL_ASSETS_PATH / model_name

        if not model_path.exists():
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

        config_file = model_path / "config.json"
        style_vec_file = model_path / "style_vectors.npy"
        safetensors_files = list(model_path.glob("*.safetensors"))

        if not config_file.exists():
            raise HTTPException(status_code=404, detail="config.json not found")
        if not safetensors_files:
            raise HTTPException(status_code=404, detail="No safetensors file found")
        if not style_vec_file.exists():
            raise HTTPException(status_code=404, detail="style_vectors.npy not found")

        model_file = max(safetensors_files, key=lambda p: p.stat().st_mtime)
        logger.info("Loading model: %s", model_name)

        tts_model = TTSModel(
            model_path=model_file,
            config_path=config_file,
            style_vec_path=style_vec_file,
            device="cpu",
        )
        # 明示的にモデルをロード（遅延ロードのため）
        tts_model.load()
        # float16モデルをfloat32に変換（CPU環境対応）
        # プライベート属性__net_gは_TTSModel__net_gでアクセス
        net_g = getattr(tts_model, "_TTSModel__net_g", None)
        if net_g is not None:
            # 全パラメータとバッファを明示的にfloat32に変換
            for param in net_g.parameters():
                param.data = param.data.float()
            for buf in net_g.buffers():
                buf.data = buf.data.float()
            logger.info("Converted model %s to float32", model_name)
        _models[model_name] = tts_model

    return _models[model_name]


def get_default_model() -> str:
    """デフォルトモデル名を取得"""
    default = config.get("default_model")
    if default:
        return default
    models = list_available_models()
    if not models:
        raise HTTPException(status_code=503, detail="No models available")
    return models[0]


# リクエストモデル
class SynthesizeRequest(BaseModel):
    text: str = Field(...)
    model: Optional[str] = None
    style: str = "Neutral"
    style_weight: float = Field(1.0, ge=0.0, le=10.0)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    sdp_ratio: float = Field(0.2, ge=0.0, le=1.0)
    noise_scale: float = Field(0.6, ge=0.0, le=1.0)
    noise_scale_w: float = Field(0.8, ge=0.0, le=1.0)
    format: str = Field("mp3", pattern=r"^(wav|mp3|ogg)$")


_FORMATS_REQUIRING_CONVERSION = {"mp3", "ogg"}


def _convert_audio(wav_data: bytes, output_format: str) -> bytes:
    """WAVデータを指定フォーマットに変換（ffmpeg使用）."""
    # ホワイトリスト検証（深層防御）
    if output_format not in _FORMATS_REQUIRING_CONVERSION:
        raise ValueError(f"サポートされていない出力フォーマット: {output_format}")

    ffmpeg_args = [
        "ffmpeg", "-loglevel", "error",
        "-i", "pipe:0",
        "-f", output_format,
    ]
    # MP3の場合はビットレートを指定
    if output_format == "mp3":
        ffmpeg_args.extend(["-ab", "128k"])
    ffmpeg_args.extend(["-ac", "1", "pipe:1"])

    try:
        process = subprocess.run(
            ffmpeg_args,
            input=wav_data,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        logger.error(
            "ffmpeg変換タイムアウト: format=%s, input_size=%d",
            output_format, len(wav_data),
        )
        raise RuntimeError("音声フォーマット変換がタイムアウトしました") from e

    if process.returncode != 0:
        logger.error(
            "ffmpeg変換エラー (returncode=%d): %s",
            process.returncode,
            process.stderr.decode(errors="replace"),
        )
        raise RuntimeError("音声フォーマット変換に失敗しました")
    return process.stdout


# エンドポイント
@app.get("/health")
async def health_check():
    return {"status": "healthy", "models_available": len(list_available_models())}


@app.get("/models")
async def get_models():
    return {"models": list_available_models(), "default": config.get("default_model")}


@app.get("/models/{model_name}/styles")
async def get_model_styles(model_name: str):
    model = get_model(model_name)
    return {"model": model_name, "styles": list(model.style2id.keys())}


@app.get("/synthesize")
async def synthesize_get(
    text: str = Query(...),
    model: Optional[str] = None,
    style: str = "Neutral",
    style_weight: float = Query(1.0, ge=0.0, le=10.0),
    speed: float = Query(1.0, ge=0.5, le=2.0),
    sdp_ratio: float = Query(0.2, ge=0.0, le=1.0),
    noise_scale: float = Query(0.6, ge=0.0, le=1.0),
    noise_scale_w: float = Query(0.8, ge=0.0, le=1.0),
    format: str = Query("mp3", pattern=r"^(wav|mp3|ogg)$"),
):
    return await _synthesize(
        text, model, style, style_weight, speed, sdp_ratio, noise_scale, noise_scale_w,
        format,
    )


@app.post("/synthesize")
async def synthesize_post(request: SynthesizeRequest):
    return await _synthesize(
        request.text,
        request.model,
        request.style,
        request.style_weight,
        request.speed,
        request.sdp_ratio,
        request.noise_scale,
        request.noise_scale_w,
        request.format,
    )


async def _synthesize(
    text: str,
    model: Optional[str],
    style: str,
    style_weight: float,
    speed: float,
    sdp_ratio: float,
    noise_scale: float,
    noise_scale_w: float,
    format: str = "mp3",
) -> Response:
    # テキスト長のバリデーション（config.ymlから読み込み）
    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long. Maximum length is {MAX_TEXT_LENGTH} characters.",
        )

    model_name = model or get_default_model()

    try:
        tts_model = get_model(model_name)

        if style not in tts_model.style2id:
            raise HTTPException(
                status_code=400,
                detail=f"Style '{style}' not found. Available: {list(tts_model.style2id.keys())}",
            )

        text_preview = text[:50] + "..." if len(text) > 50 else text
        logger.info(
            "Synthesizing: model=%s, text_length=%d, format=%s, preview=%s",
            model_name, len(text), format, text_preview,
        )

        sr, audio = tts_model.infer(
            text=text,
            style=style,
            style_weight=style_weight,
            sdp_ratio=sdp_ratio,
            noise=noise_scale,
            noise_w=noise_scale_w,
            length=1.0 / speed,
        )

        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sr, audio)
        wav_data = wav_buffer.getvalue()

        # フォーマット変換
        if format == "wav":
            content = wav_data
        else:
            content = _convert_audio(wav_data, format)

        media_type = FORMAT_MEDIA_TYPES[format]
        return Response(
            content=content,
            media_type=media_type,
            headers={"X-Model": model_name, "X-Style": style},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Synthesis error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Internal server error occurred during synthesis."
        )
