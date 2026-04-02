"""OpenAI Function Calling用ツール定義."""

# Orchestratorが使用するツール（=Agent）の定義
# OpenAI Function Calling形式に準拠
ORCHESTRATOR_TOOLS = [
    {
        "type": "function",
        "function": {
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
    },
    {
        "type": "function",
        "function": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "hypothesis_analyze",
            "description": (
                "スレッドのコメントで意見が明確に割れている場合に使う。"
                "対立する主張を抽出し、Web検索で根拠を集め、"
                "どちらの主張がより支持されるか結論を出す。"
                "detective_investigateの後に、意見対立が検出された場合にのみ呼ぶべき。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
