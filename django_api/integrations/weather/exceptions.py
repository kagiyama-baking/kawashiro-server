"""Weather app custom exceptions."""


class WeatherError(Exception):
    """Base exception for weather-related errors."""


class WeatherAPIError(WeatherError):
    """Error occurred while fetching data from weather API."""


class WeatherNetworkError(WeatherAPIError):
    """Network error when connecting to weather API."""


class WeatherTimeoutError(WeatherAPIError):
    """Timeout error when connecting to weather API."""


class WeatherParseError(WeatherAPIError):
    """Error parsing weather API response."""


class WeatherAreaNotFoundError(WeatherAPIError):
    """Specified area code not found in API response."""
