"""Weather app custom exceptions."""


class WeatherError(Exception):
    """Base exception for weather-related errors."""


class JMAAPIError(WeatherError):
    """Error occurred while fetching data from JMA API."""


class JMANetworkError(JMAAPIError):
    """Network error when connecting to JMA API."""


class JMATimeoutError(JMAAPIError):
    """Timeout error when connecting to JMA API."""


class JMAParseError(JMAAPIError):
    """Error parsing JMA API response."""


class JMAAreaNotFoundError(JMAAPIError):
    """Specified area code not found in API response."""
