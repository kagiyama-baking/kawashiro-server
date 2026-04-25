"""Tests for talk chat (multi-turn) functionality."""

import base64
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from features.talk.exceptions import PlaceholderDataMissingError
from features.talk.models import TalkConfig
from features.talk.serializers import (
    ChatRequestSerializer,
    ChatResponseSerializer,
)
from features.talk.services import TalkService
from integrations.langfuse.models import LangfusePromptRef
from integrations.tts.client import TTSResult


@pytest.fixture(autouse=True)
def _disable_langfuse_client():
    """Langfuse 接続を切って fallback_text 経由に統一する."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture
def chat_prompt_refs(db):
    sys_ref = LangfusePromptRef.objects.create(
        name="talk-chat-system",
        langfuse_prompt_name="talk-chat-system",
        fallback_text="あなたは親切なアシスタントです。",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="talk-chat-user",
        langfuse_prompt_name="talk-chat-user",
        fallback_text="dummy user prompt",
    )
    return sys_ref, user_ref


@pytest.fixture
def chat_config(chat_prompt_refs):
    return TalkConfig.objects.create(
        name="chat_test",
        display_name="チャットテスト設定",
        tts_enabled=False,
        system_prompt_ref=chat_prompt_refs[0],
        user_prompt_ref=chat_prompt_refs[1],
    )


@pytest.fixture
def chat_config_with_tts(chat_prompt_refs):
    return TalkConfig.objects.create(
        name="chat_tts_test",
        display_name="チャットTTSテスト設定",
        tts_enabled=True,
        tts_model="test_model",
        tts_style="Happy",
        system_prompt_ref=chat_prompt_refs[0],
        user_prompt_ref=chat_prompt_refs[1],
    )


def _mock_chat_completion(content: str):
    """LLMClient.chat_completion の戻り値モックを生成."""
    response = MagicMock()
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response.choices = [choice]
    return response


# ------- シリアライザのテスト -------


class TestChatRequestSerializer:
    """ChatRequestSerializer のテスト"""

    def test_valid_single_message(self):
        data = {
            "config_name": "chat",
            "messages": [{"role": "user", "content": "こんにちは"}],
        }
        serializer = ChatRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_valid_multi_turn(self):
        data = {
            "config_name": "chat",
            "messages": [
                {"role": "user", "content": "こんにちは"},
                {
                    "role": "assistant",
                    "content": "こんにちは、何かお手伝いしましょうか",
                },
                {"role": "user", "content": "今日の天気は？"},
            ],
        }
        serializer = ChatRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_config_name(self):
        data = {"messages": [{"role": "user", "content": "テスト"}]}
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "config_name" in serializer.errors

    def test_messages_required(self):
        data = {"config_name": "chat"}
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "messages" in serializer.errors

    def test_empty_messages_rejected(self):
        data = {"config_name": "chat", "messages": []}
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "messages" in serializer.errors

    def test_invalid_role_rejected(self):
        data = {
            "config_name": "chat",
            "messages": [{"role": "system", "content": "テスト"}],
        }
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()

    def test_last_message_must_be_user(self):
        data = {
            "config_name": "chat",
            "messages": [
                {"role": "user", "content": "こんにちは"},
                {"role": "assistant", "content": "こんにちは"},
            ],
        }
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "messages" in serializer.errors

    def test_messages_count_over_50_rejected(self):
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(51)]
        data = {"config_name": "chat", "messages": msgs}
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "messages" in serializer.errors

    def test_messages_count_50_accepted(self):
        # 50 件、末尾が user になるよう調整
        msgs = []
        for i in range(49):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append({"role": role, "content": f"msg{i}"})
        msgs.append({"role": "user", "content": "msg49"})
        data = {"config_name": "chat", "messages": msgs}
        serializer = ChatRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_content_max_length_4000(self):
        data = {
            "config_name": "chat",
            "messages": [{"role": "user", "content": "あ" * 4000}],
        }
        serializer = ChatRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_content_over_max_length_rejected(self):
        data = {
            "config_name": "chat",
            "messages": [{"role": "user", "content": "あ" * 4001}],
        }
        serializer = ChatRequestSerializer(data=data)
        assert not serializer.is_valid()


class TestChatResponseSerializer:
    """ChatResponseSerializer のテスト"""

    def test_valid_response_without_audio(self):
        data = {"message": {"role": "assistant", "content": "返答です"}}
        serializer = ChatResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_valid_response_with_audio(self):
        data = {
            "message": {"role": "assistant", "content": "返答です"},
            "audio_data": "ZmFrZQ==",
            "audio_format": "wav",
        }
        serializer = ChatResponseSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_message_rejected(self):
        data = {}
        serializer = ChatResponseSerializer(data=data)
        assert not serializer.is_valid()
        assert "message" in serializer.errors


# ------- サービスのテスト -------


@pytest.mark.django_db
class TestTalkServiceChat:
    """TalkService.synthesize_chat のテスト"""

    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_single_turn(self, mock_llm_class, chat_config):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion(
            "こんにちは、先輩"
        )
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "こんにちは"}],
        )

        assert result["message"]["role"] == "assistant"
        assert result["message"]["content"] == "こんにちは、先輩"
        assert "audio_data" not in result

        sent_messages = mock_llm.chat_completion.call_args.args[0]
        assert sent_messages[0]["role"] == "system"
        assert sent_messages[1]["role"] == "user"
        assert sent_messages[1]["content"] == "こんにちは"

    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_multi_turn_passes_full_history(
        self, mock_llm_class, chat_config
    ):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("最近どうですか")
        mock_llm_class.return_value = mock_llm

        messages = [
            {"role": "user", "content": "こんにちは"},
            {"role": "assistant", "content": "こんにちは"},
            {"role": "user", "content": "今日の調子はどう？"},
        ]
        service = TalkService()
        result = service.synthesize_chat(config=chat_config, messages=messages)

        assert result["message"]["content"] == "最近どうですか"

        sent = mock_llm.chat_completion.call_args.args[0]
        assert sent[0]["role"] == "system"
        assert len(sent) == 4
        assert [m["content"] for m in sent[1:]] == [
            "こんにちは",
            "こんにちは",
            "今日の調子はどう？",
        ]

    @patch("features.talk.services.LLMClient")
    @patch("features.talk.services.TTSClient")
    def test_synthesize_chat_with_tts(
        self, mock_tts_class, mock_llm_class, chat_config_with_tts
    ):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("お返事です")
        mock_llm_class.return_value = mock_llm

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = TTSResult(
            audio_data=b"fake_wav", content_type="audio/wav", format="wav"
        )
        mock_tts_class.return_value = mock_tts

        service = TalkService()
        result = service.synthesize_chat(
            config=chat_config_with_tts,
            messages=[{"role": "user", "content": "テスト"}],
        )

        assert result["audio_data"] == b"fake_wav"
        assert result["audio_format"] == "wav"
        mock_tts.synthesize.assert_called_once()
        assert mock_tts.synthesize.call_args.kwargs["text"] == "お返事です"

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_expands_system_placeholder(
        self, mock_llm_class, mock_holiday_class, db
    ):
        sys_ref = LangfusePromptRef.objects.create(
            name="chat-sys-dt",
            langfuse_prompt_name="chat-sys-dt",
            fallback_text="現在時刻: {{datetime}}",
        )
        user_ref = LangfusePromptRef.objects.create(
            name="chat-usr-dt",
            langfuse_prompt_name="chat-usr-dt",
            fallback_text="dummy",
        )
        config = TalkConfig.objects.create(
            name="chat_with_dt",
            display_name="日時付きチャット",
            system_prompt_ref=sys_ref,
            user_prompt_ref=user_ref,
        )

        mock_holiday = MagicMock()
        mock_holiday.get_holiday_name.return_value = None
        mock_holiday_class.return_value = mock_holiday

        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("OK")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        service.synthesize_chat(
            config=config,
            messages=[{"role": "user", "content": "今何時？"}],
        )

        sent_system = mock_llm.chat_completion.call_args.args[0][0]["content"]
        assert "{{datetime}}" not in sent_system
        assert "day_of_week" in sent_system

    def test_synthesize_chat_weather_requires_area_code(self, db):
        sys_ref = LangfusePromptRef.objects.create(
            name="chat-sys-w",
            langfuse_prompt_name="chat-sys-w",
            fallback_text="天気: {{weather}}",
        )
        user_ref = LangfusePromptRef.objects.create(
            name="chat-usr-w",
            langfuse_prompt_name="chat-usr-w",
            fallback_text="dummy",
        )
        config = TalkConfig.objects.create(
            name="chat_no_area",
            display_name="天気付きだが area_code なし",
            area_code="",
            system_prompt_ref=sys_ref,
            user_prompt_ref=user_ref,
        )

        service = TalkService()
        with pytest.raises(PlaceholderDataMissingError):
            service.synthesize_chat(
                config=config,
                messages=[{"role": "user", "content": "テスト"}],
            )

    @patch("features.talk.services.HolidayClient")
    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_does_not_expand_user_messages(
        self, mock_llm_class, mock_holiday_class, chat_config
    ):
        """user メッセージ内の {{datetime}} は展開しない（純粋な対話）."""
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("OK")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "今日は {{datetime}} です"}],
        )

        sent = mock_llm.chat_completion.call_args.args[0]
        assert sent[1]["content"] == "今日は {{datetime}} です"
        # system_prompt にプレースホルダーが無いので、祝日 API も呼ばれない
        mock_holiday_class.return_value.get_holiday_name.assert_not_called()


# ------- ビューのテスト -------


@pytest.mark.django_db
class TestTalkChatView:
    """TalkChatView のテスト"""

    @pytest.fixture
    def url(self):
        return reverse("talk:chat")

    @pytest.fixture
    def request_data(self, chat_config):
        return {
            "config_name": chat_config.name,
            "messages": [{"role": "user", "content": "こんにちは"}],
        }

    def test_chat_unauthorized(self, api_client, url, chat_config):
        response = api_client.post(
            url,
            {
                "config_name": chat_config.name,
                "messages": [{"role": "user", "content": "test"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_chat_config_not_found(self, authenticated_client, url):
        response = authenticated_client.post(
            url,
            {
                "config_name": "nonexistent",
                "messages": [{"role": "user", "content": "test"}],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.data

    def test_chat_missing_messages(self, authenticated_client, url, chat_config):
        response = authenticated_client.post(
            url,
            {"config_name": chat_config.name},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_empty_messages(self, authenticated_client, url, chat_config):
        response = authenticated_client.post(
            url,
            {"config_name": chat_config.name, "messages": []},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_last_role_must_be_user(self, authenticated_client, url, chat_config):
        response = authenticated_client.post(
            url,
            {
                "config_name": chat_config.name,
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "hello"},
                ],
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("features.talk.views.TalkService")
    def test_chat_success(
        self,
        mock_service_class,
        authenticated_client,
        url,
        chat_config,
        request_data,
    ):
        mock_service = MagicMock()
        mock_service.synthesize_chat.return_value = {
            "message": {"role": "assistant", "content": "返事です"},
        }
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"]["content"] == "返事です"
        assert response.data["audio_data"] is None

        mock_service.synthesize_chat.assert_called_once()
        kwargs = mock_service.synthesize_chat.call_args.kwargs
        assert kwargs["config"].name == chat_config.name
        assert kwargs["messages"] == request_data["messages"]

    @patch("features.talk.views.TalkService")
    def test_chat_with_tts_returns_base64(
        self,
        mock_service_class,
        authenticated_client,
        url,
        chat_config_with_tts,
    ):
        mock_service = MagicMock()
        mock_service.synthesize_chat.return_value = {
            "message": {"role": "assistant", "content": "TTS応答"},
            "audio_data": b"fake_wav",
            "audio_content_type": "audio/wav",
            "audio_format": "wav",
        }
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            url,
            {
                "config_name": chat_config_with_tts.name,
                "messages": [{"role": "user", "content": "音声で"}],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["audio_data"] == base64.b64encode(b"fake_wav").decode(
            "ascii"
        )
        assert response.data["audio_format"] == "wav"

    @patch("features.talk.views.TalkService")
    def test_chat_llm_timeout(
        self, mock_service_class, authenticated_client, url, request_data
    ):
        from integrations.llm.exceptions import LLMTimeoutError

        mock_service = MagicMock()
        mock_service.synthesize_chat.side_effect = LLMTimeoutError("Timeout")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT

    @patch("features.talk.views.TalkService")
    def test_chat_llm_client_error(
        self, mock_service_class, authenticated_client, url, request_data
    ):
        from integrations.llm.exceptions import LLMClientError

        mock_service = MagicMock()
        mock_service.synthesize_chat.side_effect = LLMClientError("API err")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    @patch("features.talk.views.TalkService")
    def test_chat_placeholder_data_missing(
        self, mock_service_class, authenticated_client, url, request_data
    ):
        mock_service = MagicMock()
        mock_service.synthesize_chat.side_effect = PlaceholderDataMissingError(
            "area_code 未設定"
        )
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("features.talk.views.TalkService")
    def test_chat_weather_area_not_found(
        self, mock_service_class, authenticated_client, url, request_data
    ):
        from integrations.weather.exceptions import WeatherAreaNotFoundError

        mock_service = MagicMock()
        mock_service.synthesize_chat.side_effect = WeatherAreaNotFoundError("nope")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("features.talk.views.TalkService")
    def test_chat_configuration_error(
        self, mock_service_class, authenticated_client, url, request_data
    ):
        from integrations.msgraph.exceptions import ConfigurationError

        mock_service = MagicMock()
        mock_service.synthesize_chat.side_effect = ConfigurationError("Config")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("features.talk.views.TalkService")
    def test_chat_unexpected_error(
        self, mock_service_class, authenticated_client, url, request_data
    ):
        mock_service = MagicMock()
        mock_service.synthesize_chat.side_effect = RuntimeError("Unexpected")
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(url, request_data, format="json")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @patch(
        "rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES",
        {"talk_chat": "1/minute"},
    )
    @patch("features.talk.views.TalkService")
    def test_chat_rate_limited_when_quota_exceeded(
        self,
        mock_service_class,
        authenticated_client,
        url,
        chat_config,
    ):
        """レート制限上限を超えると 429 を返す."""
        from django.core.cache import cache

        # 前テストの throttle カウンタをリセット
        cache.clear()

        mock_service = MagicMock()
        mock_service.synthesize_chat.return_value = {
            "message": {"role": "assistant", "content": "OK"},
        }
        mock_service_class.return_value = mock_service

        payload = {
            "config_name": chat_config.name,
            "messages": [{"role": "user", "content": "test"}],
        }

        first = authenticated_client.post(url, payload, format="json")
        assert first.status_code == status.HTTP_200_OK

        second = authenticated_client.post(url, payload, format="json")
        assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestTalkServiceChatMaxTokens:
    """LLM 呼び出し時に max_tokens 上限が指定されることのテスト"""

    @patch("features.talk.services.LLMClient")
    def test_synthesize_chat_passes_max_tokens(self, mock_llm_class, chat_config):
        mock_llm = MagicMock()
        mock_llm.chat_completion.return_value = _mock_chat_completion("OK")
        mock_llm_class.return_value = mock_llm

        service = TalkService()
        service.synthesize_chat(
            config=chat_config,
            messages=[{"role": "user", "content": "test"}],
        )

        call_kwargs = mock_llm.chat_completion.call_args.kwargs
        assert call_kwargs.get("max_tokens") == TalkService.CHAT_MAX_OUTPUT_TOKENS
