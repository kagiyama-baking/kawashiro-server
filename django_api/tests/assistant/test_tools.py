"""Tests for Function Calling tools."""

from unittest.mock import Mock

import pytest

from assistant.exceptions import ToolExecutionError
from assistant.tools import ASSISTANT_TOOLS, ToolExecutor


class TestAssistantTools:
    """ツール定義のテスト."""

    def test_tools_is_list(self):
        """ツール定義がリストである."""
        assert isinstance(ASSISTANT_TOOLS, list)

    def test_tools_has_required_structure(self):
        """各ツールが必要な構造を持っている."""
        for tool in ASSISTANT_TOOLS:
            assert "type" in tool
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_get_today_events_tool_exists(self):
        """get_today_eventsツールが存在する."""
        tool_names = [tool["function"]["name"] for tool in ASSISTANT_TOOLS]
        assert "get_today_events" in tool_names

    def test_get_weather_forecast_tool_exists(self):
        """get_weather_forecastツールが存在する."""
        tool_names = [tool["function"]["name"] for tool in ASSISTANT_TOOLS]
        assert "get_weather_forecast" in tool_names

    def test_get_weather_forecast_has_area_code_param(self):
        """get_weather_forecastがarea_codeパラメータを持つ."""
        weather_tool = next(
            t
            for t in ASSISTANT_TOOLS
            if t["function"]["name"] == "get_weather_forecast"
        )
        params = weather_tool["function"]["parameters"]
        assert "area_code" in params["properties"]
        assert "area_code" in params.get("required", [])


class TestToolExecutor:
    """ToolExecutorのテスト."""

    @pytest.fixture
    def mock_outlook_client(self):
        """Outlookクライアントのモック."""
        mock = Mock()
        mock.get_calendar_events.return_value = [
            {
                "subject": "朝会",
                "start": {"dateTime": "2024-12-24T09:00:00"},
                "end": {"dateTime": "2024-12-24T09:30:00"},
                "isAllDay": False,
            },
            {
                "subject": "ランチミーティング",
                "start": {"dateTime": "2024-12-24T12:00:00"},
                "end": {"dateTime": "2024-12-24T13:00:00"},
                "isAllDay": False,
            },
        ]
        return mock

    @pytest.fixture
    def mock_weather_client(self):
        """天気クライアントのモック."""
        mock = Mock()
        mock.get_weather.return_value = {
            "area_name": "東京都 東京地方",
            "area_code": "130010",
            "date": "2024-12-24",
            "weather": "晴れ",
            "weather_code": "100",
            "temp_min": 5,
            "temp_max": 15,
            "pop_00_06": None,
            "pop_06_12": 10,
            "pop_12_18": 0,
            "pop_18_24": 0,
        }
        return mock

    @pytest.fixture
    def executor(self, mock_outlook_client, mock_weather_client):
        """ToolExecutorインスタンス."""
        return ToolExecutor(
            outlook_client=mock_outlook_client,
            weather_client=mock_weather_client,
        )

    def test_execute_get_today_events(self, executor, mock_outlook_client):
        """get_today_eventsの実行."""
        result = executor.execute("get_today_events", {})

        assert "events" in result
        assert len(result["events"]) == 2
        assert result["events"][0]["subject"] == "朝会"
        mock_outlook_client.get_calendar_events.assert_called_once()

    def test_execute_get_weather_forecast(self, executor, mock_weather_client):
        """get_weather_forecastの実行."""
        result = executor.execute(
            "get_weather_forecast",
            {"area_code": "130010", "day": 0},
        )

        assert result["area_name"] == "東京都 東京地方"
        assert result["weather"] == "晴れ"
        mock_weather_client.get_weather.assert_called_once_with("130010", 0)

    def test_execute_get_weather_forecast_default_day(
        self, executor, mock_weather_client
    ):
        """get_weather_forecastのデフォルトday値."""
        executor.execute("get_weather_forecast", {"area_code": "130010"})

        mock_weather_client.get_weather.assert_called_once_with("130010", 0)

    def test_execute_unknown_tool_raises_error(self, executor):
        """未知のツール実行でエラー."""
        with pytest.raises(ToolExecutionError) as exc_info:
            executor.execute("unknown_tool", {})

        assert "unknown_tool" in str(exc_info.value)

    def test_execute_with_outlook_error(self, executor, mock_outlook_client):
        """Outlookエラー時のハンドリング."""
        mock_outlook_client.get_calendar_events.side_effect = Exception("API Error")

        with pytest.raises(ToolExecutionError):
            executor.execute("get_today_events", {})

    def test_execute_with_weather_error(self, executor, mock_weather_client):
        """天気APIエラー時のハンドリング."""
        mock_weather_client.get_weather.side_effect = Exception("API Error")

        with pytest.raises(ToolExecutionError):
            executor.execute("get_weather_forecast", {"area_code": "130010"})

    def test_execute_from_json_string(self, executor):
        """JSON文字列からのツール実行."""
        arguments = '{"area_code": "130010", "day": 1}'
        result = executor.execute_from_json("get_weather_forecast", arguments)

        assert result["area_name"] == "東京都 東京地方"

    def test_execute_from_invalid_json_raises_error(self, executor):
        """不正なJSON文字列でエラー."""
        with pytest.raises(ToolExecutionError):
            executor.execute_from_json("get_weather_forecast", "invalid json")
