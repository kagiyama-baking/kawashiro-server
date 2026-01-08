"""Function Calling用ツール定義."""

import json
from datetime import date
from typing import Any

from .exceptions import ToolExecutionError

# Function Calling用ツール定義
ASSISTANT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_today_events",
            "description": "今日のOutlookカレンダーの予定を取得する",
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
            "name": "get_weather_forecast",
            "description": "指定地域の天気予報を取得する",
            "parameters": {
                "type": "object",
                "properties": {
                    "area_code": {
                        "type": "string",
                        "description": "予報区コード（例: 130010=東京地方）",
                    },
                    "day": {
                        "type": "integer",
                        "description": "予報日（0=今日, 1=明日, 2=明後日）",
                        "default": 0,
                    },
                },
                "required": ["area_code"],
            },
        },
    },
]


class ToolExecutor:
    """ツール実行クラス."""

    def __init__(self, outlook_client: Any, weather_client: Any):
        """初期化.

        Args:
            outlook_client: Outlookカレンダークライアント
            weather_client: 天気予報クライアント
        """
        self.outlook = outlook_client
        self.weather = weather_client

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """ツールを実行して結果を返す.

        Args:
            tool_name: ツール名
            arguments: ツール引数

        Returns:
            ツール実行結果

        Raises:
            ToolExecutionError: ツール実行エラー
        """
        if tool_name == "get_today_events":
            return self._get_today_events()
        elif tool_name == "get_weather_forecast":
            return self._get_weather_forecast(arguments)
        else:
            raise ToolExecutionError(f"Unknown tool: {tool_name}")

    def execute_from_json(self, tool_name: str, arguments_json: str) -> dict[str, Any]:
        """JSON文字列からツールを実行.

        Args:
            tool_name: ツール名
            arguments_json: JSON形式のツール引数

        Returns:
            ツール実行結果

        Raises:
            ToolExecutionError: JSON解析エラーまたはツール実行エラー
        """
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError as e:
            raise ToolExecutionError(f"Invalid JSON arguments: {e}") from e

        return self.execute(tool_name, arguments)

    def _get_today_events(self) -> dict[str, Any]:
        """今日の予定を取得.

        Returns:
            予定リストを含む辞書
        """
        try:
            today = date.today()
            events = self.outlook.get_calendar_events(today, today)
            return {"events": events}
        except Exception as e:
            raise ToolExecutionError(f"Failed to get calendar events: {e}") from e

    def _get_weather_forecast(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """天気予報を取得.

        Args:
            arguments: area_code, day を含む辞書

        Returns:
            天気予報データ
        """
        try:
            area_code = arguments["area_code"]
            day = arguments.get("day", 0)
            return self.weather.get_weather(area_code, day)
        except Exception as e:
            raise ToolExecutionError(f"Failed to get weather forecast: {e}") from e
