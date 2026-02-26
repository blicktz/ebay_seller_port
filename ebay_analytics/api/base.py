"""
Base API client for eBay APIs.

Provides common functionality including authentication, retry logic,
error handling, and rate limiting for all eBay API clients.
"""

import time
import requests
from typing import Dict, Optional, Any
from ..config import Config


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
            raise RateLimitError(
                f"Rate limit exceeded: {error_message}",
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

            except RateLimitError as e:
                # Always retry on rate limit errors
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
