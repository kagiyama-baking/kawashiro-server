"""integrations.langfuse.client のテスト."""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from integrations.langfuse.client import (
    fetch_text_prompt,
    get_prompt_with_variables,
    langfuse_session,
    resolve_prompt,
    resolve_required_prompt,
)
from integrations.langfuse.exceptions import LangfusePromptError, PromptUnavailableError
from integrations.llm.models import Prompt
from tests.fixtures.factories import PromptFactory

pytestmark = pytest.mark.django_db

CLIENT_LOGGER = "integrations.langfuse.client"
SESSION_ID = "companion/2026-11-07"


@pytest.fixture
def ref(db):
    """テスト用プロンプト参照."""
    return Prompt.objects.create(
        name="test-ref",
        langfuse_prompt_name="test-prompt",
        label="production",
        fallback_text="fallback: {{name}} ({{count}})",
    )


def _text_prompt(body):
    """SDK が返すのと同じ Text 型プロンプト（実物）を作る."""
    from langfuse.model import Prompt_Text, TextPromptClient

    return TextPromptClient(
        Prompt_Text(
            name="skill-greeting",
            prompt=body,
            version=1,
            config={},
            labels=["staging"],
            tags=[],
            type="text",
        )
    )


def _chat_prompt():
    """SDK が返すのと同じ Chat 型プロンプト（実物）を作る."""
    from langfuse.model import ChatPromptClient, Prompt_Chat

    return ChatPromptClient(
        Prompt_Chat(
            name="skill-greeting",
            prompt=[{"role": "system", "content": "本文"}],
            version=1,
            config={},
            labels=["staging"],
            tags=[],
            type="chat",
        )
    )


@pytest.mark.integration
class TestResolvePrompt:
    """resolve_prompt のテスト."""

    @patch("langfuse.get_client")
    def test_returns_langfuse_prompt_when_available(self, mock_get_client, ref):
        """Langfuse から取得成功したら compile 済みテキストを返す."""
        from langfuse.model import TextPromptClient

        mock_client = MagicMock()
        mock_prompt = MagicMock(spec=TextPromptClient)
        mock_prompt.variables = []
        mock_prompt.compile.return_value = "compiled text"
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        result = resolve_prompt(ref, name="alice", count=3)

        assert result == "compiled text"
        mock_client.get_prompt.assert_called_once_with(
            "test-prompt", label="production"
        )
        mock_prompt.compile.assert_called_once_with(name="alice", count=3)

    @patch("langfuse.get_client")
    def test_returns_fallback_when_langfuse_errors(self, mock_get_client, ref):
        """Langfuse エラー時は fallback を変数置換して返す."""
        mock_get_client.side_effect = RuntimeError("connection failed")

        result = resolve_prompt(ref, name="alice", count=3)

        assert result == "fallback: alice (3)"

    @patch("langfuse.get_client")
    def test_returns_fallback_when_prompt_not_found(self, mock_get_client, ref):
        """プロンプト未登録時も fallback を返す."""
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = Exception("Prompt not found")
        mock_get_client.return_value = mock_client

        result = resolve_prompt(ref, name="bob", count=0)

        assert result == "fallback: bob (0)"

    @patch("langfuse.get_client", side_effect=ImportError("No module"))
    def test_returns_fallback_when_import_error(self, _mock, ref):
        """langfuse 未インストール時も fallback を返す."""
        result = resolve_prompt(ref, name="bob", count=0)

        assert result == "fallback: bob (0)"

    @patch("langfuse.get_client")
    def test_fallback_keeps_unknown_placeholders(self, mock_get_client, db):
        """未知のプレースホルダーは元の `{{key}}` のまま残す."""
        mock_get_client.side_effect = RuntimeError("boom")
        ref = Prompt.objects.create(
            name="partial",
            langfuse_prompt_name="partial",
            fallback_text="hello {{name}} / {{unknown}}",
        )

        result = resolve_prompt(ref, name="world")

        assert result == "hello world / {{unknown}}"

    @patch("langfuse.get_client")
    def test_fallback_without_variables(self, mock_get_client, db):
        """variables が無くても fallback は機能する."""
        mock_get_client.side_effect = RuntimeError("boom")
        ref = Prompt.objects.create(
            name="plain",
            langfuse_prompt_name="plain",
            fallback_text="static text",
        )

        result = resolve_prompt(ref)

        assert result == "static text"

    @patch("langfuse.get_client")
    def test_resolves_label(self, mock_get_client, db):
        """staging ラベルも指定される."""
        from langfuse.model import TextPromptClient

        mock_client = MagicMock()
        mock_prompt = MagicMock(spec=TextPromptClient)
        mock_prompt.variables = []
        mock_prompt.compile.return_value = "ok"
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        ref = Prompt.objects.create(
            name="staging-ref",
            langfuse_prompt_name="hello",
            label="staging",
        )

        resolve_prompt(ref, who="there")

        mock_client.get_prompt.assert_called_once_with("hello", label="staging")


@pytest.mark.integration
class TestGetPromptWithVariables:
    """get_prompt_with_variables のテスト."""

    @patch("langfuse.get_client")
    def test_returns_variables_and_compile_from_langfuse(self, mock_get_client, ref):
        """Langfuse 取得成功時は prompt.variables と compile 関数を返す."""
        from langfuse.model import TextPromptClient

        mock_client = MagicMock()
        mock_prompt = MagicMock(spec=TextPromptClient)
        mock_prompt.variables = ["name", "count"]
        mock_prompt.compile.return_value = "compiled text"
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        compile_fn, variables = get_prompt_with_variables(ref)

        assert variables == {"name", "count"}
        assert compile_fn(name="alice", count=3) == "compiled text"
        mock_prompt.compile.assert_called_once_with(name="alice", count=3)

    @patch("langfuse.get_client")
    def test_returns_variables_extracted_from_fallback_on_error(
        self, mock_get_client, ref
    ):
        """Langfuse エラー時は fallback_text から正規表現で変数抽出する."""
        mock_get_client.side_effect = RuntimeError("connection failed")

        compile_fn, variables = get_prompt_with_variables(ref)

        # fallback_text = "fallback: {{name}} ({{count}})"
        assert variables == {"name", "count"}
        assert compile_fn(name="alice", count=3) == "fallback: alice (3)"

    @patch("langfuse.get_client", side_effect=ImportError("No module"))
    def test_returns_fallback_on_import_error(self, _mock, ref):
        """ImportError 時も fallback 経路."""
        compile_fn, variables = get_prompt_with_variables(ref)

        assert variables == {"name", "count"}
        assert compile_fn(name="bob", count=0) == "fallback: bob (0)"

    @patch("langfuse.get_client")
    def test_fallback_with_empty_template(self, mock_get_client, db):
        """変数を含まない fallback_text は空集合を返す."""
        mock_get_client.side_effect = RuntimeError("boom")
        ref = Prompt.objects.create(
            name="plain-vars",
            langfuse_prompt_name="plain-vars",
            fallback_text="no variables here",
        )

        compile_fn, variables = get_prompt_with_variables(ref)

        assert variables == set()
        assert compile_fn() == "no variables here"

    @patch("langfuse.get_client")
    def test_chat_prompt_falls_back_to_text(self, mock_get_client, ref):
        """Chat 型プロンプト（非 Text）は fallback 経路に落とす."""
        from langfuse.model import ChatPromptClient

        mock_client = MagicMock()
        mock_prompt = MagicMock(spec=ChatPromptClient)
        mock_prompt.variables = ["name", "count"]
        mock_client.get_prompt.return_value = mock_prompt
        mock_get_client.return_value = mock_client

        compile_fn, variables = get_prompt_with_variables(ref)

        # ChatPromptClient は未サポートのため fallback_text から変数抽出される
        assert variables == {"name", "count"}
        assert compile_fn(name="alice", count=3) == "fallback: alice (3)"


@pytest.mark.unit
class TestFetchTextPrompt:
    """fetch_text_prompt のテスト（fallback を持たない取得経路）."""

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_with_text_prompt_returns_body(self, mock_get_client):
        """Text 型プロンプトが取れたら本文を返す."""
        mock_get_client.return_value.get_prompt.return_value = _text_prompt("本文")

        assert fetch_text_prompt("skill-greeting", label="staging") == "本文"

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_passes_only_name_and_label_to_sdk(self, mock_get_client):
        """SDK には名前とラベルだけを渡す（fallback を渡さない）."""
        mock_client = mock_get_client.return_value
        mock_client.get_prompt.return_value = _text_prompt("本文")

        fetch_text_prompt("skill-greeting", label="staging")

        mock_client.get_prompt.assert_called_once_with(
            "skill-greeting", label="staging"
        )

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_with_placeholders_returns_them_unexpanded(
        self, mock_get_client
    ):
        """本文の `{{x}}` は展開も書き換えもせずに残す."""
        body = "{{name}} さん、{{ topic }} について"
        mock_get_client.return_value.get_prompt.return_value = _text_prompt(body)

        assert fetch_text_prompt("skill-greeting", label="staging") == body

    def test_fetch_text_prompt_with_variables_returns_body_with_them_expanded(
        self, langfuse_prompts
    ):
        """変数を渡すと、本文の `{{x}}` を SDK の compile で展開した本文を返す（値は str にする）."""
        langfuse_prompts[("hn-agent-detective-user", "production")] = (
            "タイトル: {{title}}\n{{ score_info }}（{{count}} 件）"
        )

        text = fetch_text_prompt(
            "hn-agent-detective-user",
            label="production",
            variables={"title": "記事", "score_info": "スコア: 200", "count": 3},
        )

        assert text == "タイトル: 記事\nスコア: 200（3 件）"

    def test_fetch_text_prompt_with_variables_keeps_unknown_placeholders(
        self, langfuse_prompts
    ):
        """渡していない変数の `{{x}}` は展開せずに残す."""
        langfuse_prompts[("greeting", "staging")] = "{{name}} さん、{{unknown}}"

        text = fetch_text_prompt(
            "greeting", label="staging", variables={"name": "ひな"}
        )

        assert text == "ひな さん、{{unknown}}"

    def test_fetch_text_prompt_with_variables_none_returns_body_unexpanded(
        self, langfuse_prompts
    ):
        """変数が None（既定）なら展開しない（`{{x}}` もそのまま返す）."""
        langfuse_prompts[("greeting", "staging")] = "{{name}} さん"

        assert (
            fetch_text_prompt("greeting", label="staging", variables=None)
            == "{{name}} さん"
        )

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_when_get_client_fails_raises_prompt_error(
        self, mock_get_client
    ):
        """クライアントを用意できないときは LangfusePromptError にする."""
        mock_get_client.side_effect = RuntimeError("connection failed")

        with pytest.raises(LangfusePromptError):
            fetch_text_prompt("skill-greeting", label="staging")

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_when_get_prompt_fails_raises_prompt_error(
        self, mock_get_client
    ):
        """未登録・接続失敗などで取れないときは LangfusePromptError にする."""
        mock_get_client.return_value.get_prompt.side_effect = Exception(
            "Prompt not found"
        )

        with pytest.raises(LangfusePromptError):
            fetch_text_prompt("skill-greeting", label="staging")

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_with_chat_prompt_raises_prompt_error(
        self, mock_get_client
    ):
        """Chat 型プロンプトは本文が 1 つの文字列でないので LangfusePromptError にする."""
        mock_get_client.return_value.get_prompt.return_value = _chat_prompt()

        with pytest.raises(LangfusePromptError):
            fetch_text_prompt("skill-greeting", label="staging")

    def test_fetch_text_prompt_without_langfuse_installed_raises_prompt_error(
        self, monkeypatch
    ):
        """langfuse を import できないときも LangfusePromptError にする."""
        monkeypatch.setitem(sys.modules, "langfuse", None)

        with pytest.raises(LangfusePromptError):
            fetch_text_prompt("skill-greeting", label="staging")

    @patch("langfuse.get_client")
    def test_fetch_text_prompt_on_failure_chains_original_error(self, mock_get_client):
        """元の例外を __cause__ に残し、呼び出し側が理由を記録できるようにする."""
        error = Exception("Prompt not found")
        mock_get_client.return_value.get_prompt.side_effect = error

        with pytest.raises(LangfusePromptError) as exc_info:
            fetch_text_prompt("skill-greeting", label="staging")

        assert exc_info.value.__cause__ is error

    @pytest.mark.parametrize(
        "get_prompt",
        [
            pytest.param(
                MagicMock(side_effect=Exception("Prompt not found")),
                id="fetch-error",
            ),
            pytest.param(MagicMock(return_value=_chat_prompt()), id="chat-prompt"),
        ],
    )
    @patch("langfuse.get_client")
    def test_fetch_text_prompt_on_failure_logs_warning_with_name_and_label(
        self, mock_get_client, get_prompt, caplog
    ):
        """失敗したらプロンプト名とラベルを WARNING で残す."""
        mock_get_client.return_value.get_prompt = get_prompt

        with pytest.raises(LangfusePromptError):
            fetch_text_prompt("skill-greeting", label="staging")

        [record] = [
            r for r in caplog.records if r.name == "integrations.langfuse.client"
        ]
        assert record.levelno == logging.WARNING
        assert "skill-greeting" in record.getMessage()
        assert "staging" in record.getMessage()


def _client_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """integrations.langfuse.client が出した WARNING のメッセージを返す."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == CLIENT_LOGGER and record.levelno == logging.WARNING
    ]


@pytest.mark.unit
class TestLangfuseSession:
    """langfuse_session のテスト（実物を使うもの以外は Langfuse の属性の伝播を差し替える）."""

    @pytest.fixture
    def propagate_attributes(self):
        """Langfuse の属性の伝播（`langfuse.propagate_attributes`）を差し替える."""
        with patch("langfuse.propagate_attributes") as mocked:
            yield mocked

    def test_langfuse_session_with_session_id_propagates_it_only_while_body_runs(
        self, propagate_attributes
    ):
        """セッション ID の伝播を始めてから本処理を実行し、抜けるときに解除する."""
        context = propagate_attributes.return_value

        with langfuse_session(SESSION_ID):
            propagate_attributes.assert_called_once_with(session_id=SESSION_ID)
            context.__enter__.assert_called_once_with()
            context.__exit__.assert_not_called()

        context.__exit__.assert_called_once()

    @pytest.mark.parametrize("session_id", [None, ""])
    def test_langfuse_session_without_session_id_runs_body_without_propagation(
        self, propagate_attributes, session_id
    ):
        """セッション ID がなければ（None・空文字）伝播を始めず、本処理だけを実行する."""
        body = MagicMock()

        with langfuse_session(session_id):
            body()

        body.assert_called_once_with()
        propagate_attributes.assert_not_called()

    def test_langfuse_session_when_propagation_cannot_start_warns_and_runs_body(
        self, propagate_attributes, caplog
    ):
        """伝播を始められなくても warning を出すだけで本処理を実行する（解除もしない）."""
        propagate_attributes.return_value.__enter__.side_effect = RuntimeError("boom")
        body = MagicMock()

        with langfuse_session(SESSION_ID):
            body()

        body.assert_called_once_with()
        propagate_attributes.return_value.__exit__.assert_not_called()
        assert _client_warnings(caplog) == ["Langfuse session_id 設定失敗: boom"]

    def test_langfuse_session_without_langfuse_installed_warns_and_runs_body(
        self, monkeypatch, caplog
    ):
        """langfuse を import できなくても warning を出すだけで本処理を実行する."""
        monkeypatch.setitem(sys.modules, "langfuse", None)
        body = MagicMock()

        with langfuse_session(SESSION_ID):
            body()

        body.assert_called_once_with()
        [message] = _client_warnings(caplog)
        assert message.startswith("Langfuse session_id 設定失敗: ")

    def test_langfuse_session_when_release_fails_only_warns(
        self, propagate_attributes, caplog
    ):
        """伝播を解除できなくても warning を出すだけで、例外にしない."""
        propagate_attributes.return_value.__exit__.side_effect = RuntimeError("boom")
        body = MagicMock()

        with langfuse_session(SESSION_ID):
            body()

        body.assert_called_once_with()
        assert _client_warnings(caplog) == ["Langfuse session_id 解除失敗: boom"]

    def test_langfuse_session_when_body_raises_releases_propagation_and_reraises(
        self, propagate_attributes
    ):
        """本処理の例外はそのまま送出し、伝播は解除する."""
        with (
            pytest.raises(ValueError, match="本処理の失敗"),
            langfuse_session(SESSION_ID),
        ):
            raise ValueError("本処理の失敗")

        propagate_attributes.return_value.__exit__.assert_called_once()

    def test_langfuse_session_with_real_sdk_enters_and_releases_without_warning(
        self, caplog
    ):
        """実物の propagate_attributes でも、warning を出さずに入って抜けられる."""
        body = MagicMock()

        with langfuse_session(SESSION_ID):
            body()

        body.assert_called_once_with()
        assert _client_warnings(caplog) == []


REQUIRED_PROMPT_TEXT = "システムプロンプト"
EMPTY_PROMPT_TEXTS = ["", " \n\t "]


@pytest.mark.unit
class TestResolveRequiredPrompt:
    """resolve_required_prompt（システムプロンプト。本文が空なら読めた体で続けない）."""

    def test_resolve_required_prompt_with_text_returns_stripped_text(
        self, langfuse_prompts
    ):
        """前後の空白を除いた本文を返す."""
        ref = PromptFactory.build(
            name="companion-system", fallback_text=f"\n  {REQUIRED_PROMPT_TEXT}\n"
        )

        assert resolve_required_prompt(ref) == REQUIRED_PROMPT_TEXT

    @pytest.mark.parametrize("fallback_text", EMPTY_PROMPT_TEXTS)
    def test_resolve_required_prompt_with_empty_text_raises_error_with_ref_name(
        self, langfuse_prompts, fallback_text
    ):
        """本文が空（空白だけ）なら、参照の識別名を持つ PromptUnavailableError を送出する.

        `resolve_prompt` は Langfuse から取れないと例外を出さずにフォールバックテキストへ落ちる。
        """
        ref = PromptFactory.build(name="companion-system", fallback_text=fallback_text)

        with pytest.raises(
            PromptUnavailableError, match="companion-system"
        ) as exc_info:
            resolve_required_prompt(ref)

        assert (exc_info.value.ref_name, exc_info.value.reason) == (
            "companion-system",
            "本文が空です",
        )
