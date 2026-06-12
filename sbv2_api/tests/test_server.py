"""sbv2_api server.py のテスト。"""

import pytest
from fastapi.testclient import TestClient


class TestConfig:
    def test_paths_configurable_via_env(self, server_factory, tmp_path):
        server = server_factory()
        assert str(server.MODEL_ASSETS_PATH) == str(tmp_path / "model_assets")
        assert str(server.BERT_MODEL_PATH) == str(tmp_path / "bert")

    def test_device_defaults_to_cpu(self, server_factory):
        server = server_factory()
        assert server.DEVICE == "cpu"

    def test_device_configurable_via_env(self, server_factory):
        server = server_factory(device="cuda")
        assert server.DEVICE == "cuda"

    def test_max_length_loaded_from_config(self, server_factory):
        server = server_factory(config_yaml="max_length: 42\n")
        assert server.MAX_TEXT_LENGTH == 42

    def test_max_length_defaults_when_config_missing(self, server_factory):
        server = server_factory(config_yaml=None)
        assert server.MAX_TEXT_LENGTH == 500


class TestListAvailableModels:
    def test_list_available_models_returns_sorted_model_dirs(self, server_factory):
        server = server_factory(models=("model-b", "model-a"))
        assert server.list_available_models() == ["model-a", "model-b"]

    def test_list_available_models_ignores_dirs_without_config(self, server_factory):
        server = server_factory(models=("valid-model",))
        (server.MODEL_ASSETS_PATH / "invalid-model").mkdir()
        assert server.list_available_models() == ["valid-model"]


class TestGetModel:
    def test_get_model_with_path_traversal_name_raises_400(self, server_factory):
        from fastapi import HTTPException

        server = server_factory()
        with pytest.raises(HTTPException) as exc_info:
            server.get_model("../etc")
        assert exc_info.value.status_code == 400

    def test_get_model_with_unknown_name_raises_404(self, server_factory):
        from fastapi import HTTPException

        server = server_factory()
        with pytest.raises(HTTPException) as exc_info:
            server.get_model("unknown-model")
        assert exc_info.value.status_code == 404

    def test_get_model_passes_device_from_env(self, server_factory, sbv2_stubs):
        server = server_factory(device="cuda")
        server.get_model("test-model")
        _, kwargs = sbv2_stubs.tts_model_cls.call_args
        assert kwargs["device"] == "cuda"

    def test_get_model_caches_loaded_model(self, server_factory, sbv2_stubs):
        server = server_factory()
        first = server.get_model("test-model")
        second = server.get_model("test-model")
        assert first is second
        assert sbv2_stubs.tts_model_cls.call_count == 1


class TestEndpoints:
    def test_health_check_returns_healthy_with_model_count(self, server_factory):
        server = server_factory(models=("model-a", "model-b"))
        with TestClient(server.app) as client:
            response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["models_available"] == 2

    def test_get_models_returns_model_list(self, server_factory):
        server = server_factory(
            models=("model-a",), config_yaml="default_model: model-a\n"
        )
        with TestClient(server.app) as client:
            response = client.get("/models")
        assert response.status_code == 200
        assert response.json() == {"models": ["model-a"], "default": "model-a"}

    def test_get_model_styles_returns_styles(self, server_factory):
        server = server_factory()
        with TestClient(server.app) as client:
            response = client.get("/models/test-model/styles")
        assert response.status_code == 200
        assert response.json() == {
            "model": "test-model",
            "styles": ["Neutral", "Happy"],
        }

    def test_synthesize_with_too_long_text_returns_400(self, server_factory):
        server = server_factory(config_yaml="max_length: 10\n")
        with TestClient(server.app) as client:
            response = client.get("/synthesize", params={"text": "あ" * 11})
        assert response.status_code == 400

    def test_synthesize_with_unknown_style_returns_400(self, server_factory):
        server = server_factory()
        with TestClient(server.app) as client:
            response = client.get(
                "/synthesize", params={"text": "テスト", "style": "Unknown"}
            )
        assert response.status_code == 400

    def test_synthesize_get_returns_wav_audio(self, server_factory):
        server = server_factory()
        with TestClient(server.app) as client:
            response = client.get("/synthesize", params={"text": "テスト"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["x-model"] == "test-model"
        assert response.content[:4] == b"RIFF"

    def test_synthesize_post_returns_wav_audio(self, server_factory):
        server = server_factory()
        with TestClient(server.app) as client:
            response = client.post("/synthesize", json={"text": "テスト"})
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"

    def test_synthesize_with_invalid_format_returns_validation_error(
        self, server_factory
    ):
        server = server_factory()
        with TestClient(server.app) as client:
            response = client.get(
                "/synthesize", params={"text": "テスト", "format": "flac"}
            )
        assert response.status_code == 422


class TestLifespan:
    def test_startup_loads_bert_and_preloads_tts_models(
        self, server_factory, sbv2_stubs
    ):
        server = server_factory(models=("model-a", "model-b"))
        with TestClient(server.app):
            pass
        assert sbv2_stubs.bert_models.load_model.called
        assert sbv2_stubs.bert_models.load_tokenizer.called
        # 全モデルがプリロードされている
        assert sbv2_stubs.tts_model_cls.call_count == 2


class TestConvertAudio:
    def test_convert_audio_with_unsupported_format_raises_value_error(
        self, server_factory
    ):
        server = server_factory()
        with pytest.raises(ValueError):
            server._convert_audio(b"dummy", "wav")
