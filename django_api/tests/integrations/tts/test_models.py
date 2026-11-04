"""音声合成の設定項目の抽象モデル（AbstractTTSSettings）のテスト.

`get_tts_options()` の振る舞いは、継承するモデル（`CompanionConfig`）のテストで確かめる
（抽象モデルはインスタンスを作れない）。
"""

import pytest

from features.talk.models import TalkConfig
from integrations.tts.models import AbstractTTSSettings


def _tts_field_definitions(model) -> dict:
    """モデルの TTS 項目（`tts_` で始まる列）を、定義（deconstruct）で返す."""
    return {
        field.name: field.deconstruct()
        for field in model._meta.fields
        if field.name.startswith("tts_")
    }


@pytest.mark.unit
def test_abstract_tts_settings_definition_is_abstract():
    """テーブルを持たない抽象モデル（tts アプリに migration を作らない）."""
    assert AbstractTTSSettings._meta.abstract is True


@pytest.mark.unit
def test_abstract_tts_settings_fields_match_talk_config_tts_fields():
    """TTS 項目は TalkConfig と同じ名前・型・既定値・選択肢・表示名・説明."""
    expected = _tts_field_definitions(TalkConfig)

    assert expected  # 比較の相手が空なら一致しても意味がない
    assert _tts_field_definitions(AbstractTTSSettings) == expected
