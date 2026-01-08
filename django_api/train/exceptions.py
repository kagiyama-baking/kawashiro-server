"""Custom exceptions for train diainfo API."""


class YahooNetworkError(Exception):
    """Yahoo!乗換案内へのネットワークエラー"""


class YahooTimeoutError(Exception):
    """Yahoo!乗換案内へのタイムアウト"""


class YahooParseError(Exception):
    """Yahoo!乗換案内のレスポンス解析エラー"""


class YahooRailNotFoundError(Exception):
    """路線IDが見つからない"""
