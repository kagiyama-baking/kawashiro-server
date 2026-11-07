"""Prompts（Prompt。全エージェントで共有するプロンプト）のモデルのテスト."""

import pytest
from django.core.exceptions import ValidationError

from integrations.llm.models import Prompt
from tests.fixtures.factories import PromptFactory


def _unsaved_prompt(**fields) -> Prompt:
    """保存前のプロンプト（指定しない項目は正しい値）."""
    return Prompt(**{"name": "companion-system", **fields})


@pytest.mark.unit
class TestPromptLocation:
    """モデルの置き場所（admin のグループ）・表・表示名."""

    def test_prompt_app_label_is_llm_config(self):
        """llm_config アプリのモデル（admin では AI設定のグループに出る）."""
        assert Prompt._meta.app_label == "llm_config"

    def test_prompt_db_table_is_table_created_by_langfuse_integration(self):
        """表は langfuse_integration の migration が作った表のまま（状態だけ移した）."""
        assert Prompt._meta.db_table == "langfuse_integration_langfusepromptref"

    def test_prompt_verbose_names_are_prompt_and_prompts(self):
        """admin には「Prompts」と出る."""
        assert (Prompt._meta.verbose_name, Prompt._meta.verbose_name_plural) == (
            "Prompt",
            "Prompts",
        )

    def test_prompt_has_no_langfuse_prompt_name_or_fallback_text(self):
        """名前が Langfuse のプロンプト名そのもので、フォールバックの本文は持たない."""
        names = {field.name for field in Prompt._meta.get_fields()}

        assert {"langfuse_prompt_name", "fallback_text"}.isdisjoint(names)


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptValidation:
    """名前の入力チェック（名前は Langfuse のプロンプト名になる）."""

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("companion-system", id="kebab_case"),
            pytest.param("a", id="single_char"),
            pytest.param("companion/system", id="folder"),
            pytest.param("Talk System_v2", id="space_inside_and_upper"),
            pytest.param("あいさつ", id="non_ascii"),
            pytest.param("a" * 200, id="200_chars"),
        ],
    )
    def test_prompt_name_with_valid_value_passes_validation(self, name):
        """前後に空白も改行もない 200 字以内の名前（フォルダの / と途中の空白は使える）."""
        _unsaved_prompt(name=name).full_clean()

    @pytest.mark.parametrize(
        "name",
        [
            pytest.param("", id="empty"),
            pytest.param(" ", id="space_only"),
            pytest.param(" companion", id="leading_space"),
            pytest.param("companion ", id="trailing_space"),
            pytest.param("companion\n", id="trailing_newline"),
            pytest.param("companion\nsystem", id="newline_inside"),
            pytest.param("\tcompanion", id="leading_tab"),
            pytest.param("companion\u3000", id="trailing_ideographic_space"),
            pytest.param("a" * 201, id="201_chars"),
        ],
    )
    def test_prompt_name_with_invalid_value_raises_validation_error(self, name):
        """空・前後の空白や改行・途中の改行・200 字超の名前は拒む."""
        with pytest.raises(ValidationError) as exc_info:
            _unsaved_prompt(name=name).full_clean()

        assert "name" in exc_info.value.message_dict

    def test_save_with_invalid_name_raises_validation_error_and_saves_nothing(self):
        """save() は入力チェックを通してから保存する（コードから作っても通らない）."""
        with pytest.raises(ValidationError):
            Prompt.objects.create(name="companion ")

        assert not Prompt.objects.filter(name__startswith="companion").exists()

    def test_save_with_registered_name_raises_validation_error(self):
        """登録済みの名前では保存しない（名前は一意）."""
        PromptFactory(name="companion-system", label="staging")

        with pytest.raises(ValidationError) as exc_info:
            Prompt(name="companion-system", label="production").save()

        assert "name" in exc_info.value.message_dict


@pytest.mark.integration
@pytest.mark.django_db
class TestPromptDefaults:
    """既定値と表示."""

    def test_creates_with_production_label_and_empty_description(self):
        """ラベルの既定は production、説明は空."""
        prompt = Prompt.objects.create(name="companion-system")

        assert (prompt.label, prompt.description) == ("production", "")

    def test_str_returns_name_and_label(self):
        """表示は「名前@ラベル」（本文を取る Langfuse のプロンプトとその版）."""
        prompt = PromptFactory(name="companion-system", label="staging")

        assert str(prompt) == "companion-system@staging"
