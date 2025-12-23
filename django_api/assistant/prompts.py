"""プロンプトテンプレート."""

GREETING_SYSTEM_PROMPT = """あなたは親しみやすいアシスタントです。
ユーザーに{greeting_type}の挨拶をし、今日の予定と天気をわかりやすく伝えてください。

挨拶のトーン:
- morning: 明るく元気に「おはようございます」から始める
- afternoon: 落ち着いた感じで「こんにちは」から始める
- evening: 穏やかに「こんばんは」から始める

ルール:
- 回答は200文字以内で、自然な日本語で話してください
- TTSで読み上げるため、記号や英数字は避けてください
- 予定がない場合は「本日の予定はありません」と伝えてください
- 天気情報は簡潔に（晴れ、雨などの概要と気温のみ）
"""

CHAT_SYSTEM_PROMPT = """あなたは予定管理と天気情報を提供するアシスタントです。
ユーザーの質問に対して、必要に応じてツールを使用して情報を取得し、
わかりやすく回答してください。

利用可能なツール:
- get_today_events: 今日のカレンダー予定を取得
- get_weather_forecast: 天気予報を取得（area_code, dayパラメータ）

ルール:
- 回答は簡潔に、自然な日本語で行ってください
- 予定の詳細が必要な場合はget_today_eventsを使用してください
- 天気の質問にはget_weather_forecastを使用してください
- ツールの結果を元に、ユーザーにわかりやすく説明してください
"""

DAILY_SUMMARY_PROMPT = """以下の情報を元に、本日のサマリーを作成してください。

予定:
{events}

天気:
{weather}

ルール:
- サマリーは150文字程度で、重要なポイントを簡潔にまとめてください
- TTSで読み上げるため、記号や英数字は避けてください
- 予定がない場合は「本日の予定はありません」と伝えてください
"""

GREETING_USER_PROMPT = """以下の情報を元に、{greeting_type}の挨拶をしてください。

今日の予定:
{events}

天気情報:
{weather}
"""


def format_events_for_prompt(events: list[dict]) -> str:
    """予定リストをプロンプト用の文字列にフォーマット.

    Args:
        events: 予定リスト

    Returns:
        フォーマットされた文字列
    """
    if not events:
        return "予定なし"

    lines = []
    for event in events:
        subject = event.get("subject", "件名なし")
        start = event.get("start", {}).get("dateTime", "")
        if start:
            # ISO形式から時刻部分を抽出
            time_part = start.split("T")[1][:5] if "T" in start else ""
            lines.append(f"- {time_part} {subject}")
        else:
            lines.append(f"- {subject}")
    return "\n".join(lines)


def format_weather_for_prompt(weather: dict) -> str:
    """天気情報をプロンプト用の文字列にフォーマット.

    Args:
        weather: 天気情報辞書

    Returns:
        フォーマットされた文字列
    """
    if not weather:
        return "天気情報なし"

    area_name = weather.get("area_name", "")
    weather_desc = weather.get("weather", "")
    temp_min = weather.get("temp_min")
    temp_max = weather.get("temp_max")

    temp_str = ""
    if temp_min is not None and temp_max is not None:
        temp_str = f"、最低{temp_min}度、最高{temp_max}度"
    elif temp_max is not None:
        temp_str = f"、最高{temp_max}度"

    return f"{area_name}: {weather_desc}{temp_str}"
