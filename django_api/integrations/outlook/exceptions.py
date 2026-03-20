"""Outlook APIのカスタム例外クラス"""


class OutlookError(Exception):
    """Outlook API関連の基底例外クラス"""


class CalendarError(OutlookError):
    """カレンダー操作エラー"""
