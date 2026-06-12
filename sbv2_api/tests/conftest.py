"""sbv2_api テスト用共通フィクスチャ。

style_bert_vits2 は torch 依存で巨大なため、sys.modules にスタブを
注入してインポートを回避する。server モジュールは環境変数で
パス・デバイスを設定した上で都度フレッシュにインポートする。
"""

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def sbv2_stubs(monkeypatch):
    """style_bert_vits2 パッケージをスタブ化する。"""
    pkg = types.ModuleType("style_bert_vits2")

    constants = types.ModuleType("style_bert_vits2.constants")

    class Languages:
        JP = "JP"

    constants.Languages = Languages

    nlp = types.ModuleType("style_bert_vits2.nlp")
    nlp.bert_models = MagicMock()

    tts_model_mod = types.ModuleType("style_bert_vits2.tts_model")
    tts_model_cls = MagicMock(name="TTSModel")
    tts_instance = tts_model_cls.return_value
    tts_instance.style2id = {"Neutral": 0, "Happy": 1}
    tts_instance.infer.return_value = (
        44100,
        np.zeros(4410, dtype=np.int16),
    )
    # float32変換対象のネットワークは存在しない想定（getattrでNone）
    tts_instance._TTSModel__net_g = None
    tts_model_mod.TTSModel = tts_model_cls

    monkeypatch.setitem(sys.modules, "style_bert_vits2", pkg)
    monkeypatch.setitem(sys.modules, "style_bert_vits2.constants", constants)
    monkeypatch.setitem(sys.modules, "style_bert_vits2.nlp", nlp)
    monkeypatch.setitem(sys.modules, "style_bert_vits2.tts_model", tts_model_mod)

    yield types.SimpleNamespace(
        bert_models=nlp.bert_models,
        tts_model_cls=tts_model_cls,
        tts_instance=tts_instance,
    )


def _create_model_assets(assets_dir, model_names):
    """テスト用のモデルアセットディレクトリを作成する。"""
    for name in model_names:
        model_dir = assets_dir / name
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}")
        (model_dir / "style_vectors.npy").write_bytes(b"")
        (model_dir / "model.safetensors").write_bytes(b"")


@pytest.fixture
def server_factory(monkeypatch, tmp_path):
    """環境変数を設定した上で server モジュールをインポートするファクトリ。"""

    def make(models=("test-model",), config_yaml=None, device=None):
        assets_dir = tmp_path / "model_assets"
        assets_dir.mkdir(exist_ok=True)
        _create_model_assets(assets_dir, models)

        config_path = tmp_path / "config.yml"
        if config_yaml is not None:
            config_path.write_text(config_yaml, encoding="utf-8")

        monkeypatch.setenv("SBV2_MODEL_ASSETS_PATH", str(assets_dir))
        monkeypatch.setenv("SBV2_CONFIG_PATH", str(config_path))
        monkeypatch.setenv("SBV2_BERT_MODEL_PATH", str(tmp_path / "bert"))
        if device is not None:
            monkeypatch.setenv("SBV2_DEVICE", device)

        sys.modules.pop("server", None)
        import server

        return server

    yield make
    sys.modules.pop("server", None)
