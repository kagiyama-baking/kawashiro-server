"""
Style-BERT-VITS2 読み上げAPIサーバー
Kawashiro Server 内部サービス用
"""

import io
import logging
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
    bert_models.load_model(Languages.JP, pretrained_model_name_or_path=str(BERT_MODEL_PATH))
    bert_models.load_tokenizer(Languages.JP, pretrained_model_name_or_path=str(BERT_MODEL_PATH))
    logger.info("BERT models loaded")

    models = list_available_models()
    logger.info(f"Available TTS models: {models}")


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

        model_file = sorted(safetensors_files)[-1]
        logger.info(f"Loading model: {model_name}")

        _models[model_name] = TTSModel(
            model_path=model_file,
            config_path=config_file,
            style_vec_path=style_vec_file,
            device="cpu",
        )

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
):
    return await _synthesize(
        text, model, style, style_weight, speed, sdp_ratio, noise_scale, noise_scale_w
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

        logger.info(f"Synthesizing: model={model_name}, text={text}")

        sr, audio = tts_model.infer(
            text=text,
            style=style,
            style_weight=style_weight,
            sdp_ratio=sdp_ratio,
            noise=noise_scale,
            noise_w=noise_scale_w,
            length=1.0 / speed,
        )

        buffer = io.BytesIO()
        wavfile.write(buffer, sr, audio)
        buffer.seek(0)

        return Response(
            content=buffer.read(),
            media_type="audio/wav",
            headers={"X-Model": model_name, "X-Style": style},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
