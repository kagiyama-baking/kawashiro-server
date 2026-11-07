"""音声合成の設定項目の抽象モデル（AbstractTTSSettings）のテスト.

`get_tts_options()` の振る舞いは、継承するモデル（`CompanionConfig`）のテストで確かめる
（抽象モデルはインスタンスを作れない）。
"""

import pytest

from integrations.tts.models import AbstractTTSSettings


@pytest.mark.unit
def test_abstract_tts_settings_definition_is_abstract():
    """テーブルを持たない抽象モデル（tts アプリに migration を作らない）."""
    assert AbstractTTSSettings._meta.abstract is True
