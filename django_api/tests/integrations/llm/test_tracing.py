"""Langfuse のトレース構造のテスト.

同期 → 非同期 → 同期とスレッドをまたいでも親子関係が保たれ、generation が重複しないことを
確かめる。トレースを有効にする必要があるので `tests/fixtures/trace_capture.py` を
サブプロセスで実行する（送信先はメモリ上で、LLM にも Langfuse にも送らない）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.trace_capture import COMPANION_AUDIO, COMPANION_SESSION_ID

DJANGO_API_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def captured() -> dict:
    """計装を有効にして HN 調査・Talk・Companion を実行し、記録されたスパンを返す."""
    process = subprocess.run(
        [sys.executable, "-m", "tests.fixtures.trace_capture"],
        cwd=DJANGO_API_DIR,
        env={
            **os.environ,
            "LANGFUSE_TRACING_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_BASE_URL": "http://127.0.0.1:9",
            # 親プロセスの DB 設定によらず SQLite のテスト DB を使う
            "DB_ENGINE": "",
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def _find(spans: list[dict], name: str) -> dict:
    return next(span for span in spans if span["name"] == name)


def _ancestor_names(span: dict, spans: list[dict]) -> list[str]:
    """親から順に祖先のスパン名を返す."""
    by_id = {candidate["span_id"]: candidate for candidate in spans}
    names = []
    parent_id = span["parent_id"]
    while parent_id in by_id:
        parent = by_id[parent_id]
        names.append(parent["name"])
        parent_id = parent["parent_id"]
    return names


@pytest.mark.integration
class TestTraceStructure:
    """トレース構造のテスト."""

    def test_run_finishes_with_conclusion(self, captured):
        """計装を有効にしても調査が最後まで動く."""
        assert captured["final_summary"] == "結論"

    def test_sub_agent_generation_is_nested_under_tool_and_orchestrator(self, captured):
        """サブエージェントの generation は Orchestrator → ツールの配下に入る."""
        spans = captured["spans"]
        detective = _find(spans, "invoke_agent hn-detective")

        assert _ancestor_names(detective, spans) == [
            "hn-agent/detective",
            "execute_tool detective_investigate",
            "invoke_agent hn-orchestrator",
            "hn-agent/orchestrator",
        ]

    def test_investigation_stays_in_one_trace(self, captured):
        """スレッドをまたいでも 1 つのトレースにまとまる."""
        spans = captured["spans"]
        root = _find(spans, "hn-agent/orchestrator")
        investigation = [span for span in spans if span["trace_id"] == root["trace_id"]]

        assert root["parent_id"] is None
        assert {span["name"] for span in investigation} >= {
            "invoke_agent hn-orchestrator",
            "execute_tool detective_investigate",
            "hn-agent/detective",
            "invoke_agent hn-detective",
        }

    def test_each_model_request_is_recorded_once(self, captured):
        """generation は PydanticAI の計装の 1 本だけで、二重に記録しない."""
        spans = captured["spans"]
        generations = [span for span in spans if span["name"].startswith("chat ")]

        # Orchestrator 2 回 + Detective 1 回 + Talk 3 回（ストリーミング）+ Companion 2 回
        assert len(generations) == 8
        assert {span["scope"] for span in generations} == {"pydantic-ai"}
        assert {span["scope"] for span in spans} == {"pydantic-ai", "langfuse-sdk"}

    def test_decision_log_is_recorded_on_orchestrator_span(self, captured):
        """実行後も現在のスパンが戻っていて、判断フローは Orchestrator に記録される."""
        spans = captured["spans"]
        attributes = _find(spans, "hn-agent/orchestrator")["attributes"]

        decision_log = json.loads(
            attributes["langfuse.observation.metadata.decision_log"]
        )
        assert decision_log == [
            "Step 1: detective_investigate を実行 → 成功",
            "Step 2: 結論を出力",
        ]

    def test_async_observe_serializes_django_model_input(self, captured):
        """async メソッドの @observe でも Django モデルの入力を記録できる."""
        spans = captured["spans"]
        attributes = _find(spans, "hn-agent/detective")["attributes"]

        logged = json.loads(attributes["langfuse.observation.input"])
        assert logged["args"][0]["hn_id"] == 4242

    def test_session_id_reaches_generation(self, captured):
        """Talk の session_id は配下の generation まで伝播する."""
        spans = captured["spans"]
        talk = _find(spans, "invoke_agent talk-chat")
        generation = next(
            span
            for span in spans
            if span["name"].startswith("chat ") and span["parent_id"] == talk["span_id"]
        )

        assert _ancestor_names(talk, spans) == ["talk/chat"]
        assert generation["attributes"]["session.id"] == "trace-session"

    def test_investigation_uses_one_conversation_id(self, captured):
        """調査全体で会話 ID が 1 つになり、Langfuse のセッションが実行ごとに増えない.

        Langfuse は `gen_ai.conversation.id` をセッションとして扱い、省略すると
        エージェントの実行ごとに別の UUID になる。
        """
        spans = captured["spans"]
        root = _find(spans, "hn-agent/orchestrator")
        conversation_ids = {
            span["attributes"]["gen_ai.conversation.id"]
            for span in spans
            if span["trace_id"] == root["trace_id"]
            and "gen_ai.conversation.id" in span["attributes"]
        }

        assert conversation_ids == {"hn-thread/4242"}


def _generations_of_session(spans: list[dict], session_id: str) -> list[dict]:
    return [
        span
        for span in spans
        if span["name"].startswith("chat ")
        and span["attributes"].get("session.id") == session_id
    ]


def _talk_span_of_generation(generation: dict, spans: list[dict]) -> dict:
    """generation の祖先の talk/chat スパンを返す."""
    by_id = {span["span_id"]: span for span in spans}
    span = generation
    while span["name"] != "talk/chat":
        span = by_id[span["parent_id"]]
    return span


@pytest.mark.integration
class TestStreamingTrace:
    """ストリーミングのチャットのトレース."""

    @pytest.mark.parametrize(
        "session_id", ["trace-session", "litellm-session", "stopped-session"]
    )
    def test_each_stream_records_one_generation_under_talk_chat(
        self, captured, session_id
    ):
        """1 回の実行で generation は 1 本だけで、talk/chat の配下に入る."""
        spans = captured["spans"]
        generations = _generations_of_session(spans, session_id)

        assert len(generations) == 1
        assert _ancestor_names(generations[0], spans) == [
            "invoke_agent talk-chat",
            "talk/chat",
        ]

    def test_talk_chat_records_output_without_input(self, captured):
        """talk/chat は本文を出力に記録し、入力（履歴）は generation に任せる."""
        spans = captured["spans"]
        generation = _generations_of_session(spans, "litellm-session")[0]

        attributes = _talk_span_of_generation(generation, spans)["attributes"]

        assert attributes["langfuse.observation.output"] == "本文"
        assert "langfuse.observation.input" not in attributes

    def test_stream_usage_breakdown_is_dropped(self, captured):
        """ストリーミングでも usage の内訳を持たない（Langfuse で二重に数えない）."""
        generation = _generations_of_session(captured["spans"], "litellm-session")[0]

        attributes = generation["attributes"]
        assert attributes["gen_ai.usage.input_tokens"] == "10"
        assert attributes["gen_ai.usage.output_tokens"] == "3"
        assert [
            key for key in attributes if key.startswith("gen_ai.usage.details")
        ] == []

    def test_stream_uses_service_name_as_conversation_id(self, captured):
        """会話 ID はサービス名（session.id があれば Langfuse はそちらを優先する）."""
        generation = _generations_of_session(captured["spans"], "litellm-session")[0]

        assert generation["attributes"]["gen_ai.conversation.id"] == "talk"

    def test_stopped_stream_ends_spans_without_error(self, captured):
        """途中で閉じてもスパンは閉じ、届いた本文を残し、エラーにしない."""
        spans = captured["spans"]
        generation = _generations_of_session(spans, "stopped-session")[0]
        talk = _talk_span_of_generation(generation, spans)

        assert "途中" in generation["attributes"]["gen_ai.output.messages"]
        assert talk["attributes"]["langfuse.observation.output"] == "途中"
        assert talk["attributes"].get("langfuse.observation.level") != "ERROR"
        assert generation["status"] != "ERROR"
        assert talk["status"] != "ERROR"

    def test_prepare_chat_is_separate_trace_without_io(self, captured):
        """プロンプトの準備は別のトレースで記録し、内容は残さない."""
        spans = captured["spans"]
        prepare = _find(spans, "talk/prepare_chat")

        assert prepare["parent_id"] is None
        assert "langfuse.observation.input" not in prepare["attributes"]
        assert "langfuse.observation.output" not in prepare["attributes"]


@pytest.mark.integration
class TestCompanionTrace:
    """Companion の実行のトレース（音声合成した実行でも音声は送らない）."""

    def test_companion_run_records_prompt_as_input_and_text_and_skill_as_output(
        self, captured
    ):
        """companion/run は発話を入力に、セリフと使ったスキルだけを出力に記録する."""
        attributes = _find(captured["spans"], "companion/run")["attributes"]

        assert json.loads(attributes["langfuse.observation.input"]) == {
            "args": ["おはよう"],
            "kwargs": {},
        }
        assert json.loads(attributes["langfuse.observation.output"]) == {
            "text": "おはよう！",
            "skill": "good-morning",
        }

    def test_companion_trace_never_contains_audio(self, captured):
        """トレースのどのスパンにも音声のデータは載らない."""
        spans = captured["spans"]
        root = _find(spans, "companion/run")
        trace = [span for span in spans if span["trace_id"] == root["trace_id"]]

        assert root["parent_id"] is None
        assert [
            span["name"]
            for span in trace
            if COMPANION_AUDIO.decode() in json.dumps(span, ensure_ascii=False)
        ] == []

    def test_companion_skill_load_is_nested_under_agent_and_companion_run(
        self, captured
    ):
        """スキルの読み込みはエージェントの実行の配下、エージェントは companion/run の配下."""
        spans = captured["spans"]
        load = _find(spans, "execute_tool load_capability")

        assert _ancestor_names(load, spans)[-2:] == [
            "invoke_agent companion",
            "companion/run",
        ]

    def test_companion_trace_is_in_session_of_the_day(self, captured):
        """ルートの companion/run から generation まで、トレースのどのスパンもその日のセッションに入る.

        Langfuse の Sessions には session.id を持つトレースが並ぶ（会話 ID はサービス名の
        companion のままだが、session.id が優先される）。
        """
        spans = captured["spans"]
        root = _find(spans, "companion/run")
        trace = [span for span in spans if span["trace_id"] == root["trace_id"]]
        names = [span["name"] for span in trace]

        assert {"invoke_agent companion", "execute_tool load_capability"} <= set(names)
        # スキルの読み込みと最後の応答の 2 回
        assert len([name for name in names if name.startswith("chat ")]) == 2
        assert [
            (span["name"], span["attributes"].get("session.id")) for span in trace
        ] == [(span["name"], COMPANION_SESSION_ID) for span in trace]


IMPORT_CHECK_CODE = """
import json
import sys

import django

django.setup()

import django_api.urls
import features.companion.services
import features.hn_agent.orchestrator
import features.hn_agent.tasks
import features.talk.services

print(json.dumps(sorted(sys.modules)))
"""


@pytest.mark.integration
def test_app_startup_does_not_import_replaced_llm_stack():
    """起動と機能モジュールの import で旧スタックを読み込まない.

    `langfuse.openai` は import するだけで OpenAI SDK を書き換え、PydanticAI の計装と
    generation が二重になるので、間接的にも読み込まれないことを確かめる。
    """
    process = subprocess.run(
        [sys.executable, "-c", IMPORT_CHECK_CODE],
        cwd=DJANGO_API_DIR,
        env={**os.environ, "DB_ENGINE": ""},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    modules = set(json.loads(process.stdout))

    assert "features.talk.services" in modules
    assert "pydantic_ai" in modules
    forbidden = [
        name
        for name in modules
        if name == "langfuse.openai"
        or name.split(".")[0] in {"langchain_core", "langchain_openai", "langgraph"}
    ]
    assert forbidden == []
