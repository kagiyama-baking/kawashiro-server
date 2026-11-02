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

DJANGO_API_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def captured() -> dict:
    """計装を有効にして HN 調査と Talk を実行し、記録されたスパンを返す."""
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

        # Orchestrator 2 回 + Detective 1 回 + Talk 1 回
        assert len(generations) == 4
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


IMPORT_CHECK_CODE = """
import json
import sys

import django

django.setup()

import django_api.urls
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
