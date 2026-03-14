# eBay API Rate Limit Research & Adaptation Plan

**Date**: 2026-03-01
**Purpose**: Research eBay Analytics API rate limits and adapt traffic sync scripts to prevent rate limiting

---

## Executive Summary

The eBay Sell Analytics API has a **500 calls per day limit**, significantly lower than initially assumed. Current implementation uses hardcoded limits (50 calls/60 seconds) that don't match eBay's actual quota system. This document outlines research findings and proposes changes to:
1. Use actual rate limits from eBay's getRateLimits API
2. Implement intelligent wait-and-resume when rate limits are hit
3. Add more conservative delays to prevent limit triggers
4. Monitor quota usage in real-time
5. Enable fully unattended operation with automatic resumption

---

## Research Findings

### eBay Analytics API Rate Limits

Based on official eBay Developer documentation and testing:

| Limit Type | Value | Time Window | Source |
|------------|-------|-------------|--------|
| **Daily Limit** | 500 calls | 86,400 seconds (24 hours) | Official API Docs |
| **Short-duration Limit** | Unknown (suspected ~50 calls) | 300 seconds (5 minutes) | Inferred from docs |
| **Per-endpoint granularity** | No | N/A | All sell.analytics endpoints share quota |

**Key Documentation Sources:**
- Main limits page: https://developer.ebay.com/develop/get-started/api-call-limits
- Analytics overview: https://developer.ebay.com/api-docs/developer/analytics/overview.html
- getRateLimits method: https://developer.ebay.com/api-docs/developer/analytics/resources/rate_limit/methods/getRateLimits

### Official Rate Limit Response Structure

eBay's Analytics API provides rate limit information via the `getRateLimits` endpoint:

```json
{
  "rateLimits": [
    {
      "apiName": "sell.analytics",
      "apiContext": "sell",
      "resources": [
        {
          "name": "sell.analytics.traffic_report",
          "rates": [
            {
              "count": 150,           // Calls made in window
              "limit": 500,           // Total quota
              "remaining": 350,       // Calls remaining
              "reset": "2026-03-02T00:00:00Z",  // When quota resets
              "timeWindow": 86400     // Window duration (seconds)
            },
            {
              "count": 25,
              "limit": 50,            // Suspected short-duration limit
              "remaining": 25,
              "reset": "2026-03-01T14:05:00Z",
              "timeWindow": 300       // 5-minute window
            }
          ]
        }
      ]
    }
  ]
}
```

**Note**: The exact short-duration limit values need to be confirmed by calling getRateLimits with your actual API credentials.

---

## Current Implementation Analysis

### API Call Patterns

**Current script**: `ebay_analytics/services/traffic_sync.py`

For a 7-day sync with 539 active listings:
- Active listings: 3 batches per day (200 + 200 + 139)
- Sold listings: Variable (depends on recent sales)
- **Total per day**: ~3-6 API calls
- **7-day sync**: 21-42 total calls (well under daily 500 limit)

### Existing Rate Limit Protection

#### 1. Between-Batch Delays
**Location**: `ebay_analytics/api/analytics.py:214-217, 285-288`
```python
delay = 3.0  # 3 seconds between batches
```

#### 2. Between-Day Delays
**Location**: `ebay_analytics/services/traffic_sync.py:164-168`
```python
delay = self.config.api_call_delay_seconds  # Default: 5.0 seconds
```

#### 3. Sliding Window Protection
**Location**: `ebay_analytics/api/base.py:151-179`
```python
max_calls = 50  # Assumed limit (unverified)
window_seconds = 60  # 1-minute window (may be incorrect)
```

#### 4. Retry Logic with Exponential Backoff
**Location**: `ebay_analytics/api/base.py:181-263`
- Retries on 429 (Rate Limit) errors up to 3 times
- Exponential backoff: 2s → 4s → 8s
- **Problem**: Continues retrying instead of stopping immediately

### Current Configuration (.env)

```bash
API_MAX_RETRIES=3
API_RETRY_DELAY=2.0
API_TIMEOUT=30
API_RATE_LIMIT_MAX_CALLS=50        # INCORRECT: Should be 500/day
API_RATE_LIMIT_WINDOW=60           # INCORRECT: Should be 86400 (daily)
API_CALL_DELAY_SECONDS=5.0         # Between days
```

---

## API Testing Results (2026-03-01)

To verify eBay's rate limit implementation, we created a test script (`scripts/test_token_and_limits.py`) and executed it against the live eBay API.

### Test 1: Sell Analytics API (traffic_report endpoint)

**Endpoint**: `GET https://api.ebay.com/sell/analytics/v1/traffic_report`

**Result**: ✅ **SUCCESS**
- HTTP Status: 200 OK
- Successfully retrieved 200 traffic records
- Access token is valid and working

**Response Headers Analysis**:
```
rlogid: t6pitusquq%60fiiw%3F%3Ctowtwwvpd%60jhs.2bd6fea73%3F*w%60ut27%3F*wck%3Ed-19cac1fd944-0x2352
x-ebay-svc-tracking-data: <a>bs=0&ul=en-US&serviceCorrelationId=01KJP1ZPA8RMKZH25CDA29602V...</a>
Content-Type: application/json
x-envoy-upstream-service-time: 1430
Server: ebay-proxy-server
Cache-Control: max-age=0, no-cache, no-store
```

**Critical Finding**: ❌ **No rate limit headers present**
- No `X-RateLimit-Limit` header
- No `X-RateLimit-Remaining` header
- No `X-RateLimit-Reset` header
- No quota information in response headers

### Test 2: Developer Analytics API (getRateLimits endpoint)

**Endpoint**: `GET https://api.ebay.com/developer/analytics/v1_beta/rate_limit/`

**Parameters**:
```json
{
  "api_name": "sell.analytics",
  "api_context": "sell"
}
```

**Result**: ⚠️ **204 No Content**
- HTTP Status: 204 No Content
- Request was successful (not a 401 authentication error)
- But returned **no rate limit data**

**Interpretation**:
- The getRateLimits API is accessible with our OAuth token
- However, it does not provide rate limit information for `sell.analytics`
- This API may only track certain other eBay APIs, or may not have data available yet
- **Cannot be used for proactive rate limit monitoring**

### Test 3: Rate Limit Detection Strategy

**Conclusion from Testing**:

Since eBay does not provide:
1. Rate limit information via the Developer Analytics API
2. Rate limit headers in API responses

**We must rely on**:
1. **429 Error Responses** - The only way to detect rate limit violations
2. **Conservative delays** - Prevent hitting limits through spacing
3. **In-memory call tracking** - Estimate usage during script execution
4. **Smart error parsing** - Extract reset time from 429 error body

**429 Error Response Format** (expected):
```json
{
  "errors": [
    {
      "errorId": 429,
      "domain": "API_ANALYTICS",
      "category": "REQUEST",
      "message": "Rate limit exceeded. Try again after 300 seconds.",
      "parameters": [
        {
          "name": "resetTime",
          "value": "2026-03-01T14:05:00Z"
        }
      ]
    }
  ]
}
```

**Implementation Impact**:
- ✅ Can implement: In-memory call tracking, conservative delays, wait-and-resume
- ❌ Cannot implement: Proactive quota checking, real-time remaining calls display
- ⚠️ Must implement: Robust 429 error parsing and intelligent waiting

---

## Problems Identified

### 1. Incorrect Hardcoded Limits
**Issue**: Code assumes 50 calls/60 seconds, but eBay uses 500 calls/day + possible 5-minute windows
**Impact**: Rate limit protection may be too aggressive or too lenient
**Location**: `ebay_analytics/api/base.py:151-179`

### 2. Retry Logic Continues After Rate Limits
**Issue**: When 429 error occurs, script retries up to 3 times with exponential backoff
**Impact**: Wastes time with retries instead of intelligently waiting for quota reset
**Location**: `ebay_analytics/api/base.py:181-263`

### 3. No Dynamic Rate Limit Checking
**Issue**: Never queries eBay's getRateLimits to see actual quota
**Impact**: No visibility into how close to limits we are
**Missing**: No implementation of getRateLimits API call

### 4. Insufficient Delay Spacing
**Issue**: 3-second batch delays and 5-second day delays may be too short
**Impact**: Bursts of API calls could trigger short-duration limits
**Location**: Multiple files

### 5. No Rate Limit Header Monitoring
**Issue**: Doesn't check X-RateLimit-* headers in responses (if eBay provides them)
**Impact**: Missing real-time quota information
**Location**: `ebay_analytics/api/base.py`

### 6. No Quota Usage Visibility
**Issue**: User can't see how many calls remain or when quota resets
**Impact**: Hard to plan sync frequency or troubleshoot limit issues
**Missing**: Quota tracking and display

---

## Proposed Solution

### Strategy Overview

1. **Query actual limits** from eBay before starting sync
2. **Use conservative delays** to prevent bursts
3. **Wait and resume intelligently** when rate limits are hit
4. **Monitor quota** throughout execution
5. **Provide visibility** into remaining calls and reset times
6. **Enable unattended operation** - script runs autonomously without manual intervention

### Implementation Plan

#### Phase 1: Add In-Memory API Call Tracking

**⚠️ TESTING RESULTS (2026-03-01):**
- eBay's `getRateLimits` API returns **204 No Content** for `sell.analytics` - not usable
- eBay **does not return rate limit headers** (X-RateLimit-*) in API responses
- **Must rely on 429 error responses** to detect rate limit violations
- Will track API calls manually in-memory during script execution

**File**: `ebay_analytics/api/base.py`

Add call tracking to BaseAPIClient:
```python
class BaseAPIClient:
    def __init__(self, config: Config):
        # ... existing init ...
        self.api_call_count = 0
        self.session_start_time = time.time()
        self.api_call_history = []  # List of (timestamp, endpoint) tuples

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with call tracking."""

        # Track this API call
        self.api_call_count += 1
        self.api_call_history.append((time.time(), url))

        # ... existing request logic ...

        return response.json()

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for current session."""
        duration = time.time() - self.session_start_time
        return {
            "total_calls": self.api_call_count,
            "duration_seconds": duration,
            "calls_per_minute": self.api_call_count / (duration / 60) if duration > 0 else 0
        }
```

**File**: `ebay_analytics/services/traffic_sync.py`

Add session tracking display:
```python
def sync_traffic_data(self, days_back: int = 7) -> None:
    """Sync traffic data with session tracking."""

    # Display estimated API usage
    print("\n📊 Estimated API Usage:")
    # Estimate based on listing count
    # Assuming 3-6 calls per day (batches of 200 listings)
    estimated_calls = days_back * 6  # Conservative estimate
    print(f"   Syncing {days_back} days")
    print(f"   Estimated API calls: ~{estimated_calls}")
    print(f"   Daily limit: 500 calls")
    print(f"   Short-duration limit: ~50 calls per 5 minutes (estimated)")
    print()

    # ... existing sync logic ...

    # Display session statistics at end
    print("\n📊 API Usage Statistics:")
    stats = self.analytics_client.client.get_session_stats()
    print(f"   Total API calls: {stats['total_calls']}")
    print(f"   Duration: {stats['duration_seconds']:.1f} seconds")
    print(f"   Rate: {stats['calls_per_minute']:.2f} calls/minute")
    print(f"   Remaining daily quota (estimated): {500 - stats['total_calls']}")
    print()
```

#### Phase 2: Implement Smart Wait-and-Resume on Rate Limits

**File**: `ebay_analytics/api/base.py`

Add new exception:
```python
class RateLimitExceededError(APIError):
    """
    Raised when eBay API rate limit is exceeded.
    Contains reset time information for intelligent waiting.
    """
    def __init__(self, message: str, reset_time: Optional[str] = None,
                 time_window: Optional[int] = None, limit_type: str = "unknown"):
        super().__init__(message)
        self.reset_time = reset_time
        self.time_window = time_window  # Seconds (300 or 86400)
        self.limit_type = limit_type    # "short-duration" or "daily"
```

Add helper function to calculate wait time:
```python
def _calculate_wait_time(reset_time_str: str) -> int:
    """
    Calculate seconds to wait until rate limit resets.

    Args:
        reset_time_str: ISO 8601 timestamp or Unix epoch

    Returns:
        Seconds to wait (minimum 1)
    """
    try:
        # Try parsing as ISO 8601
        from datetime import datetime
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
```

Modify `_make_request()` retry logic:
```python
def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
    """Make HTTP request with intelligent rate limit handling."""

    for attempt in range(max_retries):
        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)

            if response.status_code == 429:
                # Rate limit exceeded - parse reset information
                reset_time = response.headers.get("X-RateLimit-Reset")
                remaining = response.headers.get("X-RateLimit-Remaining", "0")
                limit = response.headers.get("X-RateLimit-Limit", "unknown")

                # Try to determine which limit was hit from response
                # eBay may return multiple rate limit headers or error details
                limit_type = "unknown"
                time_window = None

                # Check error response body for more details
                try:
                    error_data = response.json()
                    error_msg = error_data.get("errors", [{}])[0].get("message", "")
                    if "daily" in error_msg.lower():
                        limit_type = "daily"
                        time_window = 86400
                    elif "minute" in error_msg.lower() or "short" in error_msg.lower():
                        limit_type = "short-duration"
                        time_window = 300
                except:
                    pass

                raise RateLimitExceededError(
                    f"eBay API rate limit exceeded ({remaining}/{limit} remaining). "
                    f"Quota resets at: {reset_time}",
                    reset_time=reset_time,
                    time_window=time_window,
                    limit_type=limit_type
                )

            # ... rest of error handling (other status codes)

        except RateLimitExceededError:
            # Don't retry here - let caller handle the waiting strategy
            raise

        except (RequestException, Timeout, ConnectionError) as e:
            # Network errors - still retry with backoff
            if attempt < max_retries - 1:
                delay = retry_delay * (2 ** attempt)
                time.sleep(delay)
            else:
                raise APIError(f"Network error after {max_retries} retries: {e}")
```

**File**: `ebay_analytics/services/traffic_sync.py`

Add smart wait-and-resume handler:
```python
def _wait_for_rate_limit_reset(self, error: RateLimitExceededError,
                                max_wait_seconds: int = 86400) -> bool:
    """
    Wait intelligently for rate limit to reset, then resume.

    Args:
        error: The RateLimitExceededError with reset information
        max_wait_seconds: Maximum time to wait (default: 24 hours)

    Returns:
        True if we should resume, False if we should abort
    """
    from datetime import datetime, timedelta

    print(f"\n⏸️  RATE LIMIT HIT: {error}")

    if not error.reset_time:
        print("   ⚠️  No reset time provided. Using default 5-minute wait.")
        wait_seconds = 300
    else:
        wait_seconds = _calculate_wait_time(error.reset_time)

    # Check if wait time is reasonable
    if wait_seconds > max_wait_seconds:
        print(f"   ❌ Reset time is {wait_seconds/3600:.1f} hours away (max: {max_wait_seconds/3600:.1f} hours).")
        print(f"   This exceeds maximum wait time. Script will abort.")
        return False

    if wait_seconds < 0:
        print(f"   ⚠️  Reset time appears to be in the past. Retrying immediately.")
        return True

    # Display wait information
    limit_description = {
        "short-duration": "5-minute rate limit",
        "daily": "daily rate limit",
        "unknown": "rate limit"
    }.get(error.limit_type, "rate limit")

    print(f"   Limit type: {limit_description}")
    print(f"   Resets at: {error.reset_time}")
    print(f"   Wait time: {wait_seconds} seconds ({wait_seconds/60:.1f} minutes)")
    print(f"\n   🕐 Pausing script to respect {limit_description}...")
    print(f"   The script will automatically resume when the quota resets.")
    print(f"   You can safely leave this running.\n")

    # Add small buffer to ensure quota has definitely reset
    buffer_seconds = 10
    total_wait = wait_seconds + buffer_seconds

    # Wait with progress updates
    start_time = time.time()
    last_update = 0

    while time.time() - start_time < total_wait:
        elapsed = int(time.time() - start_time)
        remaining = total_wait - elapsed

        # Update every 30 seconds for short waits, every 5 minutes for long waits
        update_interval = 30 if total_wait < 600 else 300

        if elapsed - last_update >= update_interval:
            if remaining >= 3600:
                print(f"   ⏳ Waiting... {remaining/3600:.1f} hours remaining until resume")
            elif remaining >= 60:
                print(f"   ⏳ Waiting... {remaining/60:.0f} minutes remaining until resume")
            else:
                print(f"   ⏳ Waiting... {remaining} seconds remaining until resume")
            last_update = elapsed

        time.sleep(1)  # Check every second

    print(f"   ✓ Rate limit should have reset. Resuming operations...")
    return True


def sync_traffic_data(self, days_back: int = 7, max_rate_limit_waits: int = 10) -> None:
    """
    Sync traffic data with intelligent rate limit handling.

    Args:
        days_back: Number of days to sync
        max_rate_limit_waits: Maximum number of times to wait for rate limits
                             (prevents infinite loops)
    """
    rate_limit_wait_count = 0

    # ... existing setup code ...

    for day_idx, day_str in enumerate(days_to_process, start=1):
        try:
            # ... existing day processing logic ...

            # Try to get active listings data
            try:
                records = self.analytics_client.get_traffic_for_active_listings(...)

            except RateLimitExceededError as e:
                # Check if we've hit max wait attempts
                if rate_limit_wait_count >= max_rate_limit_waits:
                    print(f"\n❌ Hit rate limit {rate_limit_wait_count} times. Aborting to prevent infinite loop.")
                    print(f"   Successfully synced {synced_days} of {days_to_sync} days.")
                    return

                rate_limit_wait_count += 1

                # Wait for rate limit to reset
                should_resume = self._wait_for_rate_limit_reset(
                    e,
                    max_wait_seconds=self.config.api_rate_limit_max_wait_seconds
                )

                if not should_resume:
                    print(f"   Successfully synced {synced_days} of {days_to_sync} days before aborting.")
                    return

                # Retry this day after waiting
                print(f"\n   🔄 Retrying day {day_str}...")
                records = self.analytics_client.get_traffic_for_active_listings(...)

            # ... process records ...

        except Exception as e:
            print(f"   ✗ Unexpected error: {e}")
            continue

    print(f"\n✓ Successfully synced all {days_to_sync} days!")
    if rate_limit_wait_count > 0:
        print(f"   (Paused {rate_limit_wait_count} time(s) for rate limit resets)")
```

#### Phase 3: Increase Conservative Delays

**File**: `ebay_analytics/config.py`

Add new configuration options:
```python
@dataclass
class Config:
    # ... existing fields ...

    # Rate limiting - Conservative defaults
    api_call_delay_between_batches: float = 10.0     # Between batches (was 3.0)
    api_call_delay_between_days: float = 15.0        # Between days (was 5.0)
    api_rate_limit_safe_mode: bool = True            # Extra conservative mode
    api_rate_limit_max_wait_seconds: int = 86400     # Max time to wait for reset (24 hours)
    api_rate_limit_max_wait_count: int = 10          # Max times to wait (prevent infinite loops)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            # ... existing mappings ...
            api_call_delay_between_batches=float(os.getenv("API_CALL_DELAY_BETWEEN_BATCHES", "10.0")),
            api_call_delay_between_days=float(os.getenv("API_CALL_DELAY_BETWEEN_DAYS", "15.0")),
            api_rate_limit_safe_mode=os.getenv("API_RATE_LIMIT_SAFE_MODE", "true").lower() == "true",
            api_rate_limit_max_wait_seconds=int(os.getenv("API_RATE_LIMIT_MAX_WAIT_SECONDS", "86400")),
            api_rate_limit_max_wait_count=int(os.getenv("API_RATE_LIMIT_MAX_WAIT_COUNT", "10")),
        )
```

**File**: `ebay_analytics/api/analytics.py`

Update batch delays:
```python
if batch_num < total_batches:
    delay = self.config.api_call_delay_between_batches  # Use configurable delay
    if self.config.api_rate_limit_safe_mode:
        delay *= 1.5  # Add 50% more delay in safe mode
    print(f"   ⏱  Waiting {delay:.1f}s before next batch...")
    time.sleep(delay)
```

**File**: `ebay_analytics/services/traffic_sync.py`

Update day delays:
```python
if day_idx < days_to_sync:
    delay = self.config.api_call_delay_between_days
    if self.config.api_rate_limit_safe_mode:
        delay *= 1.5  # Add 50% more delay in safe mode
    print(f"   ⏱  Waiting {delay:.1f}s before next day...")
    time.sleep(delay)
```

#### Phase 4: Enhanced Session Statistics

**Note**: This phase consolidates with Phase 1 since we're already tracking calls in-memory.

**File**: `ebay_analytics/api/base.py`

Enhanced tracking (already covered in Phase 1):
```python
class BaseAPIClient:
    def __init__(self, config: Config):
        # ... existing init ...
        self.api_call_count = 0
        self.session_start_time = time.time()
        self.api_call_history = []  # Track timestamp and endpoint

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with call tracking."""

        # Track this API call
        self.api_call_count += 1
        self.api_call_history.append((time.time(), url))

        # ... make request ...

        # Note: eBay does NOT return rate limit headers (verified 2026-03-01)
        # Cannot monitor remaining quota from response headers

        return response.json()

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for current session."""
        duration = time.time() - self.session_start_time
        return {
            "total_calls": self.api_call_count,
            "duration_seconds": duration,
            "calls_per_minute": self.api_call_count / (duration / 60) if duration > 0 else 0,
            "estimated_remaining_daily": max(0, 500 - self.api_call_count)
        }
```

**File**: `ebay_analytics/services/traffic_sync.py`

Display stats after sync (already covered in Phase 1):
```python
def sync_traffic_data(self, days_back: int = 7) -> None:
    """Sync traffic data with session tracking."""

    # ... existing sync logic ...

    # Display session statistics at end
    print("\n📊 API Usage Statistics:")
    stats = self.analytics_client.client.get_session_stats()
    print(f"   Total API calls: {stats['total_calls']}")
    print(f"   Duration: {stats['duration_seconds']:.1f} seconds")
    print(f"   Rate: {stats['calls_per_minute']:.2f} calls/minute")
    print(f"   Remaining daily quota (estimated): {stats['estimated_remaining_daily']}")
    print()
```

#### Phase 5: Update Configuration

**File**: `.env`

Update with new values:
```bash
# eBay API Rate Limiting (Conservative Settings)
API_MAX_RETRIES=3
API_RETRY_DELAY=2.0
API_TIMEOUT=30

# Daily limit tracking (will be verified via getRateLimits)
API_RATE_LIMIT_MAX_CALLS=500       # Updated from 50
API_RATE_LIMIT_WINDOW=86400        # Updated from 60 (1 day in seconds)

# Delay settings - Conservative to prevent rate limits
API_CALL_DELAY_BETWEEN_BATCHES=10.0   # Seconds between batches (was 3.0)
API_CALL_DELAY_BETWEEN_DAYS=15.0      # Seconds between days (was 5.0)

# Safety features
API_RATE_LIMIT_SAFE_MODE=true              # Add extra delays in safe mode

# Wait-and-resume strategy
API_RATE_LIMIT_MAX_WAIT_SECONDS=86400      # Max seconds to wait for reset (24 hours)
API_RATE_LIMIT_MAX_WAIT_COUNT=10           # Max times to wait before aborting (prevents infinite loops)
```

---

## Expected Behavior After Changes

### Startup
```
📊 Estimated API Usage:
   Syncing 7 days
   Estimated API calls: ~42
   Daily limit: 500 calls
   Short-duration limit: ~50 calls per 5 minutes (estimated)

✓ Starting sync...
```

### During Sync
```
Day 2024-02-23:
   ✓ Active listings (539): 3 batches, 451 records
   ⏱  Waiting 15.0s before next day...
```

### On Rate Limit Hit (Short-Duration Limit)
```
⏸️  RATE LIMIT HIT: eBay API rate limit exceeded (0/50 remaining). Quota resets at: 2026-03-01T14:10:00Z
   Limit type: 5-minute rate limit
   Resets at: 2026-03-01T14:10:00Z
   Wait time: 300 seconds (5.0 minutes)

   🕐 Pausing script to respect 5-minute rate limit...
   The script will automatically resume when the quota resets.
   You can safely leave this running.

   ⏳ Waiting... 4 minutes remaining until resume
   ⏳ Waiting... 3 minutes remaining until resume
   ⏳ Waiting... 2 minutes remaining until resume
   ⏳ Waiting... 1 minutes remaining until resume
   ✓ Rate limit should have reset. Resuming operations...

   🔄 Retrying day 2024-02-23...
   ✓ Active listings (539): 3 batches, 451 records
```

### On Rate Limit Hit (Daily Limit - If Configured to Wait)
```
⏸️  RATE LIMIT HIT: eBay API rate limit exceeded (0/500 remaining). Quota resets at: 2026-03-02T00:00:00Z
   Limit type: daily rate limit
   Resets at: 2026-03-02T00:00:00Z
   Wait time: 43200 seconds (720.0 minutes)

   🕐 Pausing script to respect daily rate limit...
   The script will automatically resume when the quota resets.
   You can safely leave this running.

   ⏳ Waiting... 12.0 hours remaining until resume
   ⏳ Waiting... 11.9 hours remaining until resume
   [... progress updates every 5 minutes ...]
   ⏳ Waiting... 0.1 hours remaining until resume
   ✓ Rate limit should have reset. Resuming operations...
```

### On Rate Limit Hit (Max Wait Exceeded)
```
⏸️  RATE LIMIT HIT: eBay API rate limit exceeded (0/500 remaining). Quota resets at: 2026-03-03T00:00:00Z
   ❌ Reset time is 36.0 hours away (max: 24.0 hours).
   This exceeds maximum wait time. Script will abort.
   Successfully synced 4 of 7 days before aborting.
```

### Completion (With Automatic Resumption)
```
✓ Successfully synced 7 days of traffic data!
   (Paused 2 time(s) for rate limit resets)

📊 API Usage Statistics:
   Total API calls: 42
   Duration: 987.5 seconds
   Rate: 2.55 calls/minute
   Remaining daily quota (estimated): 458
```

---

## Testing Plan

### Test 1: Verify API Call Tracking
**Goal**: Confirm in-memory call tracking works correctly
**Steps**:
1. Run `poetry run python scripts/test_token_and_limits.py` to verify token
2. Run sync for 3 days with small listing count
3. Verify session statistics are displayed at end
4. Check that call count matches expected (3-6 calls per day)

**Expected Result**:
- Session stats show accurate call count
- Duration and calls/minute are calculated correctly
- Estimated remaining quota is displayed

### Test 2: Simulate Rate Limit Hit and Wait-Resume
**Goal**: Confirm script waits and automatically resumes after rate limit
**Steps**:
1. Temporarily set `API_RATE_LIMIT_MAX_WAIT_SECONDS=300` (5 minutes max wait)
2. Simulate hitting a 5-minute rate limit by making rapid API calls
3. Verify script pauses and displays countdown timer
4. Confirm script resumes after wait period
5. Verify the same day is retried successfully after resumption

**Expected Result**:
- Script pauses with clear countdown display
- No 429 error retries during wait
- Automatically resumes after reset time
- Successfully completes the previously failed operation

### Test 3: Conservative Delay Timing
**Goal**: Verify delays prevent bursts
**Steps**:
1. Enable safe mode: `API_RATE_LIMIT_SAFE_MODE=true`
2. Run sync for 3 days
3. Measure time between API calls

**Expected Result**:
- Between batches: 15s (10s base + 50% safe mode)
- Between days: 22.5s (15s base + 50% safe mode)

### Test 4: Long-Running Sync
**Goal**: Confirm script can run for extended periods
**Steps**:
1. Sync 30 days of data
2. Monitor for rate limit warnings
3. Verify no 429 errors occur

**Expected Result**: Completes successfully, ~180 API calls over ~90 minutes

---

## Files Modified Summary

1. **ebay_analytics/api/analytics.py**
   - Add `get_rate_limits()` method
   - Update batch delay to use config value
   - Add safe mode multiplier

2. **ebay_analytics/api/base.py**
   - Add `RateLimitExceededError` exception
   - Modify retry logic to stop on 429 errors
   - Add call tracking and session statistics
   - Monitor rate limit headers

3. **ebay_analytics/services/traffic_sync.py**
   - Add rate limit check at startup
   - Add user confirmation if quota low
   - Catch and handle `RateLimitExceededError`
   - Display session statistics at end
   - Update day delay to use config value

4. **ebay_analytics/config.py**
   - Add `api_call_delay_between_batches` field
   - Add `api_call_delay_between_days` field
   - Add `api_rate_limit_safe_mode` field
   - Add `api_rate_limit_check_on_start` field
   - Update `from_env()` method

5. **.env**
   - Update `API_RATE_LIMIT_MAX_CALLS` to 500
   - Update `API_RATE_LIMIT_WINDOW` to 86400
   - Add `API_CALL_DELAY_BETWEEN_BATCHES=10.0`
   - Add `API_CALL_DELAY_BETWEEN_DAYS=15.0`
   - Add `API_RATE_LIMIT_SAFE_MODE=true`
   - Add `API_RATE_LIMIT_CHECK_ON_START=true`

---

## Risk Assessment

### Low Risk
- Adding rate limit query (read-only operation)
- Increasing delays (just makes script slower)
- Adding monitoring/logging

### Medium Risk
- Changing retry logic (must ensure other errors still retry)
- New exception type (must handle in all calling code)

### Mitigation
- Test thoroughly with small date ranges first
- Keep old retry logic for non-429 errors
- Add comprehensive error messages
- Log all API calls and responses

---

## Future Enhancements

### Phase 6: Adaptive Rate Limiting
- Automatically adjust delays based on remaining quota
- Speed up when quota is plentiful
- Slow down when approaching limits

### Phase 7: Persistent Quota Tracking
- Store API call history in database
- Track daily usage patterns
- Predict when safe to run large syncs

### Phase 8: Advanced Scheduling & Notifications
- Email/webhook notifications when script pauses for rate limits
- Schedule syncs at optimal times based on historical quota usage
- Distributed sync strategy: automatically split large date ranges across multiple days if daily limits would be exceeded

---

## Conclusion

The current implementation has rate limit protection but uses incorrect assumptions about eBay's quota system. Testing revealed that eBay does not provide rate limit information via API responses or headers, requiring a different approach. By implementing these changes, the script will:

1. **Track API calls in-memory** to estimate quota usage during execution
2. **Wait and resume automatically** when 429 errors occur (no manual intervention required)
3. **Use conservative delays** to prevent triggering limits in the first place (10s between batches, 15s between days)
4. **Provide visibility** into estimated quota usage with session statistics
5. **Run unattended** for extended periods, pausing and resuming as needed
6. **Prevent repeated violations** by parsing reset times from 429 error responses and waiting appropriately

The 500 calls/day limit is generous for typical usage (7-day sync = ~40 calls), but short-duration limits (likely 50 calls per 5 minutes) may still be triggered. The wait-and-resume strategy ensures the script can handle both limit types intelligently, pausing for minutes or hours as needed, then automatically continuing where it left off - all without requiring human intervention.

**Key Finding**: eBay's getRateLimits API returns 204 No Content and response headers do not include rate limit information. Rate limits can only be detected via 429 error responses, making conservative delays and smart error handling essential.
