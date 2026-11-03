"""Talk テスト共通フィクスチャ."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from features.talk.llm_agents import TALK_CHAT_AGENT, TALK_TITLE_AGENT
from features.talk.models import ChatMessage, ChatSession, TalkConfig
from integrations.langfuse.models import LangfusePromptRef
from integrations.tts.client import TTSResult
from tests.fixtures.llm import ScriptedLLM, make_llm_settings


@pytest.fixture
def talk_llm_settings():
    """LLM 接続設定を固定する（DB の LLMServiceConfig に依存させない）."""
    with patch(
        "features.talk.services.get_llm_settings",
        return_value=make_llm_settings("talk"),
    ) as mock_get_settings:
        yield mock_get_settings


@pytest.fixture
def chat_llm(talk_llm_settings):
    """チャットエージェントの応答を台本で固定する."""
    llm = ScriptedLLM()
    with TALK_CHAT_AGENT.override(model=llm.model):
        yield llm


@pytest.fixture
def title_llm(talk_llm_settings):
    """タイトル生成エージェントの応答を台本で固定する（台本が尽きると生成失敗になる）."""
    llm = ScriptedLLM()
    with TALK_TITLE_AGENT.override(model=llm.model):
        yield llm


@pytest.fixture
def talk_prompt_refs(db):
    """テスト用システム/ユーザープロンプト参照を用意する.

    TalkConfig に付ける汎用参照。fallback_text はテンプレート変数
    `{{weather}}` `{{events}}` `{{datetime}}` を含める。
    """
    system_ref = LangfusePromptRef.objects.create(
        name="talk-test-system",
        langfuse_prompt_name="talk-test-system",
        fallback_text="テスト用システムプロンプト",
    )
    user_ref = LangfusePromptRef.objects.create(
        name="talk-test-user",
        langfuse_prompt_name="talk-test-user",
        fallback_text=(
            "テンプレ: weather={{weather}} events={{events}} datetime={{datetime}}"
        ),
    )
    return {"system": system_ref, "user": user_ref}


# 以下はチャットのターン（test_chat_turn_*.py）のフィクスチャ。
# 同名のフィクスチャを定義しているテストモジュールでは、そちらが優先される。


@pytest.fixture
def media_root(settings, tmp_path):
    """音声の保存先をテストごとの一時ディレクトリにする."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def chat_turn_env(media_root):
    """Langfuse から切り離す（スロットルの計数は `tests/conftest.py` が毎回空にする）."""
    with patch("langfuse.get_client", side_effect=RuntimeError("disabled in tests")):
        yield


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        email="chat-turn@example.com", password="dummypass1234"
    )


@pytest.fixture
def auth_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def prompt_refs(db):
    return (
        LangfusePromptRef.objects.create(
            name="chat-turn-system",
            langfuse_prompt_name="chat-turn-system",
            fallback_text="あなたは親切な AI です。",
        ),
        LangfusePromptRef.objects.create(
            name="chat-turn-user",
            langfuse_prompt_name="chat-turn-user",
            fallback_text="dummy",
        ),
    )


@pytest.fixture
def talk_config(prompt_refs):
    return TalkConfig.objects.create(
        name="chat-turn",
        display_name="チャットのターン",
        system_prompt_ref=prompt_refs[0],
        user_prompt_ref=prompt_refs[1],
    )


@pytest.fixture
def tts_config(prompt_refs):
    return TalkConfig.objects.create(
        name="chat-turn-tts",
        display_name="チャットのターン（音声あり）",
        tts_enabled=True,
        tts_format="wav",
        tts_model="model",
        system_prompt_ref=prompt_refs[0],
        user_prompt_ref=prompt_refs[1],
    )


@pytest.fixture
def session(user, talk_config):
    return ChatSession.objects.create(user=user, config_name=talk_config.name)


@pytest.fixture
def tts_session(user, tts_config):
    return ChatSession.objects.create(user=user, config_name=tts_config.name)


@pytest.fixture
def mock_tts():
    """TTS の結果を固定する（既定は音声 8 バイト）."""
    with patch("features.talk.services.TTSClient") as mock_tts_class:
        client = mock_tts_class.return_value
        client.synthesize.return_value = TTSResult(
            audio_data=b"\x00" * 8, content_type="audio/wav", format="wav"
        )
        yield client


@pytest.fixture
def conversation(session):
    """user/assistant が 2 往復入ったセッションを作る（assistant には音声あり）."""
    messages = []
    for sequence in range(4):
        message = ChatMessage(
            session=session,
            sequence=sequence,
            role="user" if sequence % 2 == 0 else "assistant",
            content=f"#{sequence}",
        )
        if sequence % 2 == 1:
            message.audio_format = "wav"
            message.audio_size_bytes = 30
            message.audio_file.save(
                f"{sequence}.wav", ContentFile(b"\x02" * 30), save=False
            )
        message.save()
        messages.append(message)
    return messages
