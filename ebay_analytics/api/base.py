"""
Base API client for eBay APIs.

Provides common functionality including authentication, retry logic,
error handling, and rate limiting for all eBay API clients.
"""

import time
import requests
from typing import Dict, Optional, Any
from datetime import datetime
from ..config import Config


def calculate_wait_time(reset_time_str: str) -> int:
    """
    Calculate seconds to wait until rate limit resets.

    Args:
        reset_time_str: ISO 8601 timestamp or Unix epoch

    Returns:
        Seconds to wait (minimum 1)
    """
    try:
        # Try parsing as ISO 8601
        reset_dt = datetime.fromisoformat(reset_time_str.replace('Z', '+00:00'))
        now_dt = datetime.now(reset_dt.tzinfo)
        wait_seconds = int((reset_dt - now_dt).total_seconds())

    except (ValueError, AttributeError):
        try:
            # Try parsing as Unix timestamp
            reset_timestamp = int(reset_time_str)
            wait_seconds = reset_timestamp - int(time.time())
        except (ValueError, TypeError):
            # Default fallback: 5 minutes
            wait_seconds = 300

    return max(1, wait_seconds)  # Always wait at least 1 second


class APIError(Exception):
    """Base exception for API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[requests.Response] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class AuthenticationError(APIError):
    """Raised when authentication fails (401)."""
    pass


class RateLimitError(APIError):
    """Raised when rate limit is exceeded (429)."""
    pass


class RateLimitExceededError(APIError):
    """
    Raised when eBay API rate limit is exceeded.
    Contains reset time information for intelligent waiting.
    """
    def __init__(
        self,
        message: str,
        reset_time: Optional[str] = None,
        time_window: Optional[int] = None,
        limit_type: str = "unknown",
        status_code: Optional[int] = None,
        response: Optional[requests.Response] = None
    ):
        super().__init__(message, status_code, response)
        self.reset_time = reset_time
        self.time_window = time_window  # Seconds (300 or 86400)
        self.limit_type = limit_type    # "short-duration" or "daily"


class NotFoundError(APIError):
    """Raised when resource is not found (404)."""
    pass


class BaseAPIClient:
    """
    Base client for eBay APIs with common functionality.

    Provides:
    - Authentication headers
    - Automatic retry with exponential backoff
    - Error handling and meaningful exceptions
    - Rate limiting handling
    """

    def __init__(self, config: Config):
        """
        Initialize base API client.

        Args:
            config: Configuration object with API credentials
        """
        self.config = config
        self.session = requests.Session()
        self.call_history = []  # Track API call timestamps for rate limiting

        # Session statistics tracking
        self.api_call_count = 0
        self.session_start_time = time.time()
        self.api_call_history = []  # List of (timestamp, url) tuples

        self._setup_session()

    def _setup_session(self):
        """Configure session with default headers."""
        self.session.headers.update({
            'Authorization': f'Bearer {self.config.ebay_access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })

    def _get_headers(self, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Get headers for API request.

        Args:
            additional_headers: Optional additional headers to include

        Returns:
            Dictionary of headers
        """
        headers = self.session.headers.copy()

        if additional_headers:
            headers.update(additional_headers)

        return dict(headers)

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Handle API response and raise appropriate exceptions.

        Args:
            response: requests Response object

        Returns:
            Parsed JSON response

        Raises:
            AuthenticationError: If authentication fails (401)
            RateLimitError: If rate limit exceeded (429)
            NotFoundError: If resource not found (404)
            APIError: For other API errors
        """
        # Success responses
        if response.status_code in (200, 201, 204):
            if response.content:
                try:
                    return response.json()
                except ValueError:
                    return {'content': response.text}
            return {}

        # Error responses
        error_message = f"API request failed with status {response.status_code}"

        try:
            error_data = response.json()
            if 'errors' in error_data and error_data['errors']:
                error_message = error_data['errors'][0].get('message', error_message)
            elif 'error_description' in error_data:
                error_message = error_data['error_description']
            elif 'message' in error_data:
                error_message = error_data['message']
        except (ValueError, KeyError):
            error_message = response.text or error_message

        # Specific error types
        if response.status_code == 401:
            raise AuthenticationError(
                f"Authentication failed: {error_message}",
                status_code=401,
                response=response
            )
        elif response.status_code == 429:
            # Parse rate limit information from error response
            reset_time = None
            limit_type = "unknown"
            time_window = None

            try:
                error_data = response.json()
                error_msg = error_message.lower()

                # Try to extract reset time from error parameters
                if 'errors' in error_data and error_data['errors']:
                    error_obj = error_data['errors'][0]
                    if 'parameters' in error_obj:
                        for param in error_obj['parameters']:
                            if param.get('name') == 'resetTime':
                                reset_time = param.get('value')
                                break

                # Determine limit type from error message
                if "daily" in error_msg:
                    limit_type = "daily"
                    time_window = 86400
                elif "minute" in error_msg or "short" in error_msg:
                    limit_type = "short-duration"
                    time_window = 300

            except (ValueError, KeyError):
                pass

            raise RateLimitExceededError(
                f"Rate limit exceeded: {error_message}",
                reset_time=reset_time,
                time_window=time_window,
                limit_type=limit_type,
                status_code=429,
                response=response
            )
        elif response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {error_message}",
                status_code=404,
                response=response
            )
        else:
            raise APIError(
                error_message,
                status_code=response.status_code,
                response=response
            )

    def _check_rate_limit(self, url: str):
        """
        Check if we're exceeding rate limits (protection against infinite loops).

        Args:
            url: The API endpoint being called

        Raises:
            APIError: If rate limit is exceeded
        """
        now = time.time()
        max_calls = self.config.api_rate_limit_max_calls
        window_seconds = self.config.api_rate_limit_window

        # Remove old calls outside the sliding window
        cutoff = now - window_seconds
        self.call_history = [t for t in self.call_history if t > cutoff]

        # Check if we're over the limit
        if len(self.call_history) >= max_calls:
            raise APIError(
                f"Rate limit protection triggered: {len(self.call_history)} calls in last {window_seconds}s "
                f"(limit: {max_calls} calls/{window_seconds}s). "
                f"Possible infinite loop detected. Check your code logic. "
                f"Endpoint: {url}"
            )

        # Record this call
        self.call_history.append(now)

    def _make_request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with automatic retry and exponential backoff.

        Args:
            method: HTTP method ('GET', 'POST', etc.)
            url: Request URL
            params: Query parameters
            data: Request body (for POST/PUT)
            headers: Additional headers
            **kwargs: Additional arguments for requests

        Returns:
            Parsed JSON response

        Raises:
            APIError: If request fails after all retries
        """
        max_retries = self.config.api_max_retries
        retry_delay = self.config.api_retry_delay
        timeout = self.config.api_timeout

        # Check rate limit before making request
        self._check_rate_limit(url)

        # Track this API call for session statistics
        self.api_call_count += 1
        self.api_call_history.append((time.time(), url))

        request_headers = self._get_headers(headers)

        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data,
                    headers=request_headers,
                    timeout=timeout,
                    **kwargs
                )

                return self._handle_response(response)

            except RateLimitExceededError:
                # Don't retry here - let caller handle wait-and-resume
                raise

            except RateLimitError as e:
                # Old-style rate limit error (shouldn't happen, but keep for backwards compatibility)
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⚠ Rate limit hit, waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"✗ Rate limit exceeded after {max_retries} retries")
                    raise

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                # Retry on network errors
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"⚠ Network error: {e}, retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise APIError(f"Request failed after {max_retries} retries: {e}")

            except AuthenticationError:
                # Don't retry authentication errors
                raise

            except APIError as e:
                # Retry on 5xx server errors, not on 4xx client errors
                if e.status_code and 500 <= e.status_code < 600 and attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"⚠ Server error ({e.status_code}), retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make GET request.

        Args:
            url: Request URL
            params: Query parameters
            headers: Additional headers
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response
        """
        return self._make_request_with_retry('GET', url, params=params, headers=headers, **kwargs)

    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make POST request.

        Args:
            url: Request URL
            data: Request body
            params: Query parameters
            headers: Additional headers
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response
        """
        return self._make_request_with_retry('POST', url, data=data, params=params, headers=headers, **kwargs)

    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get statistics for current API session.

        Returns:
            Dictionary with session statistics:
            - total_calls: Total number of API calls made
            - duration_seconds: Total session duration
            - calls_per_minute: Average API calls per minute
            - estimated_remaining_daily: Estimated remaining daily quota (based on 500/day limit)
        """
        duration = time.time() - self.session_start_time
        return {
            "total_calls": self.api_call_count,
            "duration_seconds": duration,
            "calls_per_minute": self.api_call_count / (duration / 60) if duration > 0 else 0,
            "estimated_remaining_daily": max(0, 500 - self.api_call_count)
        }

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


if __name__ == "__main__":
    # Test base API client
    from ..config import load_config

    print("Testing BaseAPIClient...")

    try:
        config = load_config()
        client = BaseAPIClient(config)

        print(f"✓ Client initialized successfully")
        print(f"  Authorization header set: {bool(client.session.headers.get('Authorization'))}")
        print(f"  Max retries: {config.api_max_retries}")
        print(f"  Retry delay: {config.api_retry_delay}s")

        client.close()
        print(f"✓ Client closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
