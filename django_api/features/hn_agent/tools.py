"""OpenAI Responses API用ツール定義."""

# Orchestratorが使用するツール（=Agent）の定義
# OpenAI Responses API形式に準拠（フラット構造）
ORCHESTRATOR_TOOLS = [
    {
        "type": "function",
        "name": "memory_search",
        "description": (
            "過去に類似するHNスレッドがあったか検索する。"
            "pgvectorのcosine similarityを使い、過去のスレッドと照合する。"
            "新しいスレッドの調査を始める際に最初に呼ぶべきツール。"
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "detective_investigate",
        "description": (
            "スレッドが急上昇している理由を調査する。"
            "HNコメントの分析、Tavilyでの背景情報検索、"
            "LLMによる総合分析を行い、レポートを生成する。"
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]
