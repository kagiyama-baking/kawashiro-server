"""Companion の実行 API（POST /companion/run/）のテスト.

実行サービスはビューが参照する名前（`features.companion.views.run_companion`）で
差し替えるので、LLM・Langfuse・音声合成は呼ばない。回数制限は `test_throttling.py`。
有効な設定がない DB では回数制限が数えないので、ここでは設定を作らない。
"""

import base64
import logging
from unittest.mock import patch

import pytest
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework import status

from features.companion.exceptions import (
    CompanionNotConfiguredError,
    PromptUnavailableError,
    UnknownSkillError,
)
from features.companion.services import CompanionReply
from integrations.llm.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMOutputError,
    LLMTimeoutError,
)
from integrations.tts.client import TTSResult
from integrations.tts.exceptions import TTSNetworkError, TTSTimeoutError

pytestmark = [pytest.mark.api, pytest.mark.django_db]

TEXT = "おはようございます。今日は晴れですね"
AUDIO = TTSResult(
    audio_data=b"RIFF\x00\x01\xfe\xff-audio", content_type="audio/wav", format="wav"
)
# 例外のメッセージに入れる内部の情報（応答に出てはいけない）
INTERNALS = "upstream: http://litellm:4000 key=sk-internal"

CONFIG_ERROR = "Companion の設定に問題があります"
LLM_TIMEOUT = "AI 生成サービスへのリクエストがタイムアウトしました"
TTS_TIMEOUT = "音声合成サービスへのリクエストがタイムアウトしました"
LLM_ERROR = "AI 生成サービスでエラーが発生しました"
TTS_ERROR = "音声合成サービスでエラーが発生しました"
UNEXPECTED_ERROR = "セリフの生成中に問題が発生しました"


@pytest.fixture
def run_companion():
    """ビューが呼ぶ実行サービスを差し替える（既定は音声なし・スキルなしのセリフ）."""
    with patch("features.companion.views.run_companion", autospec=True) as mocked:
        mocked.return_value = CompanionReply(text=TEXT, skill=None, audio=None)
        yield mocked


def _post(client, body):
    return client.post(reverse("companion:run"), body, format="json")


class TestCompanionRunViewAuth:
    """認証."""

    def test_run_without_token_returns_401(self, api_client, run_companion):
        """トークンがなければ 401 で、実行しない."""
        response = _post(api_client, {"prompt": "おはよう"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        run_companion.assert_not_called()


class TestCompanionRunViewValidation:
    """入力の検証（不正なら 400 で、実行しない）."""

    @pytest.mark.parametrize(
        ("body", "field"),
        [
            pytest.param({}, "prompt", id="missing_prompt"),
            pytest.param({"prompt": ""}, "prompt", id="empty_prompt"),
            pytest.param({"prompt": " \n\t\u3000"}, "prompt", id="whitespace_prompt"),
            pytest.param({"prompt": "あ" * 1001}, "prompt", id="prompt_1001_chars"),
            pytest.param({"prompt": ["おはよう"]}, "prompt", id="non_string_prompt"),
            pytest.param(
                {"prompt": "おはよう", "skill": "Good-Morning"}, "skill", id="uppercase"
            ),
            pytest.param(
                {"prompt": "おはよう", "skill": "good_morning"},
                "skill",
                id="underscore",
            ),
            pytest.param(
                {"prompt": "おはよう", "skill": "good--morning"},
                "skill",
                id="double_hyphen",
            ),
            pytest.param(
                {"prompt": "おはよう", "skill": "-morning"},
                "skill",
                id="leading_hyphen",
            ),
            pytest.param(
                {"prompt": "おはよう", "skill": "good:morning"}, "skill", id="colon"
            ),
            pytest.param(
                {"prompt": "おはよう", "skill": ""}, "skill", id="empty_skill"
            ),
            pytest.param(
                {"prompt": "おはよう", "skill": "a" * 65}, "skill", id="skill_65_chars"
            ),
        ],
    )
    def test_run_with_invalid_body_returns_400_without_running(
        self, authenticated_client, run_companion, body, field
    ):
        """項目ごとのエラーを返し、実行しない."""
        response = _post(authenticated_client, body)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.json()) == {field}
        run_companion.assert_not_called()

    def test_run_with_malformed_json_returns_400_detail(
        self, authenticated_client, run_companion
    ):
        """JSON として読めない本文は DRF の detail で 400 にし、実行しない."""
        response = authenticated_client.post(
            reverse("companion:run"), "{broken", content_type="application/json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.json()) == {"detail"}
        run_companion.assert_not_called()

    def test_run_with_1000_char_prompt_runs(self, authenticated_client, run_companion):
        """1000 文字の発話は受け付ける."""
        prompt = "あ" * 1000

        response = _post(authenticated_client, {"prompt": prompt})

        assert response.status_code == status.HTTP_200_OK
        run_companion.assert_called_once_with(prompt, skill=None)

    def test_run_with_unknown_skill_returns_400_with_message(
        self, authenticated_client, run_companion
    ):
        """有効な設定で選ばれていない・無効なスキルは 400 で、どのスキルかを返す."""
        run_companion.side_effect = UnknownSkillError("good-evening")

        response = _post(
            authenticated_client, {"prompt": "こんばんは", "skill": "good-evening"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {
            "error": (
                "スキル「good-evening」は有効な Companion 設定で選ばれていないか、"
                "無効です"
            )
        }


class TestCompanionRunViewSuccess:
    """成功したときの応答と、実行サービスへの渡し方."""

    def test_run_with_audio_returns_text_skill_and_base64_audio(
        self, authenticated_client, run_companion
    ):
        """音声は Base64 の文字列で返し、元のバイト列に戻せる."""
        run_companion.return_value = CompanionReply(
            text=TEXT, skill="good-morning", audio=AUDIO
        )

        response = _post(authenticated_client, {"prompt": "おはよう"})

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/json"
        body = response.json()
        assert body == {
            "text": TEXT,
            "skill": "good-morning",
            "audio_data": base64.b64encode(AUDIO.audio_data).decode("ascii"),
            "audio_format": "wav",
        }
        assert base64.b64decode(body["audio_data"]) == AUDIO.audio_data

    def test_run_without_audio_returns_null_audio_fields(
        self, authenticated_client, run_companion
    ):
        """音声合成が無効なら音声の 2 項目は null（スキルを使わなければ skill も null）."""
        response = _post(authenticated_client, {"prompt": "おはよう"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "text": TEXT,
            "skill": None,
            "audio_data": None,
            "audio_format": None,
        }

    @pytest.mark.parametrize(
        ("body", "expected_skill"),
        [
            pytest.param(
                {"prompt": "おはよう", "skill": "good-morning"},
                "good-morning",
                id="with_skill",
            ),
            pytest.param({"prompt": "おはよう"}, None, id="without_skill"),
            pytest.param({"prompt": "おはよう", "skill": None}, None, id="null_skill"),
            pytest.param(
                {"prompt": "おはよう", "skill": " good-morning\n"},
                "good-morning",
                id="skill_with_spaces",
            ),
        ],
    )
    def test_run_passes_prompt_and_skill_to_service(
        self, authenticated_client, run_companion, body, expected_skill
    ):
        """発話とスキルを渡す（スキル名は前後の空白を除く。省略・null はスキルなし）."""
        _post(authenticated_client, body)

        run_companion.assert_called_once_with("おはよう", skill=expected_skill)

    def test_run_passes_prompt_without_trimming(
        self, authenticated_client, run_companion
    ):
        """発話は前後の空白・改行も含めてそのまま渡す（Talk の発話の入力と同じ）."""
        _post(authenticated_client, {"prompt": "  おはよう\n"})

        run_companion.assert_called_once_with("  おはよう\n", skill=None)


class TestCompanionRunViewErrors:
    """実行サービスの例外と HTTP ステータスの対応（内部の情報は返さない）."""

    @pytest.mark.parametrize(
        ("exc", "status_code", "error"),
        [
            pytest.param(
                CompanionNotConfiguredError(), 503, CONFIG_ERROR, id="not_configured"
            ),
            pytest.param(
                PromptUnavailableError("companion-system"),
                503,
                CONFIG_ERROR,
                id="prompt_unavailable",
            ),
            pytest.param(
                PromptUnavailableError("companion-skill-good-night", reason=INTERNALS),
                503,
                CONFIG_ERROR,
                id="skill_body_unavailable",
            ),
            pytest.param(
                LLMConfigurationError(INTERNALS),
                503,
                CONFIG_ERROR,
                id="llm_not_configured",
            ),
            # LLMTimeoutError は LLMClientError のサブクラス。502 ではなく 504 になる
            pytest.param(
                LLMTimeoutError(INTERNALS),
                504,
                LLM_TIMEOUT,
                id="llm_timeout_not_client_error",
            ),
            pytest.param(
                TTSTimeoutError(INTERNALS), 504, TTS_TIMEOUT, id="tts_timeout"
            ),
            pytest.param(LLMClientError(INTERNALS), 502, LLM_ERROR, id="llm_client"),
            pytest.param(LLMOutputError(INTERNALS), 502, LLM_ERROR, id="llm_output"),
            pytest.param(TTSNetworkError(INTERNALS), 502, TTS_ERROR, id="tts_network"),
            pytest.param(
                RuntimeError(INTERNALS), 500, UNEXPECTED_ERROR, id="unexpected"
            ),
        ],
    )
    def test_run_service_error_returns_status_and_fixed_message(
        self, authenticated_client, run_companion, exc, status_code, error
    ):
        """決まったメッセージだけを返し、例外のメッセージは返さない."""
        run_companion.side_effect = exc

        response = _post(authenticated_client, {"prompt": "おはよう"})

        assert response.status_code == status_code
        assert response.json() == {"error": error}
        assert str(exc) not in response.content.decode()

    def test_run_unexpected_error_logs_traceback(
        self, authenticated_client, run_companion, caplog
    ):
        """想定外の例外はトレースバック付きで ERROR に記録する."""
        error = RuntimeError(INTERNALS)
        run_companion.side_effect = error

        with caplog.at_level(logging.ERROR, logger="features.companion.views"):
            _post(authenticated_client, {"prompt": "おはよう"})

        records = [r for r in caplog.records if r.name == "features.companion.views"]
        assert len(records) == 1
        assert records[0].levelno == logging.ERROR
        assert records[0].exc_info[1] is error


@pytest.fixture(scope="module")
def openapi_schema():
    """OpenAPI スキーマ（生成は重いのでモジュールで 1 回）."""
    return SchemaGenerator().get_schema(request=None, public=True)


def _component(schema, media):
    """`$ref` の先のコンポーネントを返す."""
    name = media["schema"]["$ref"].rsplit("/", 1)[-1]
    return schema["components"]["schemas"][name]


class TestCompanionRunSchema:
    """OpenAPI スキーマ."""

    def test_schema_documents_run_with_tag_and_statuses(self, openapi_schema):
        """POST /companion/run/ が companion タグで、返しうるステータスとともに載る."""
        operation = openapi_schema["paths"]["/companion/run/"]["post"]

        assert operation["tags"] == ["companion"]
        assert set(operation["responses"]) == {
            "200",
            "400",
            "401",
            "429",
            "500",
            "502",
            "503",
            "504",
        }

    def test_schema_documents_request_and_response_fields(self, openapi_schema):
        """入力は prompt（必須・1000 字まで）と skill、応答は 4 項目（3 つは null あり）."""
        operation = openapi_schema["paths"]["/companion/run/"]["post"]
        request = _component(
            openapi_schema, operation["requestBody"]["content"]["application/json"]
        )
        response = _component(
            openapi_schema, operation["responses"]["200"]["content"]["application/json"]
        )

        assert request["required"] == ["prompt"]
        assert request["properties"]["prompt"]["maxLength"] == 1000
        assert request["properties"]["skill"]["nullable"] is True
        assert set(response["properties"]) == {
            "text",
            "skill",
            "audio_data",
            "audio_format",
        }
        assert sorted(response["required"]) == sorted(response["properties"])
        assert [
            name
            for name, field in response["properties"].items()
            if field.get("nullable")
        ] == ["skill", "audio_data", "audio_format"]
