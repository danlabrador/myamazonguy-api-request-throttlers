from collections import deque
from dataclasses import dataclass, field
import math
from python.throttler import RequestThrottler
import random
import requests
import time


# If you are working with only one file, do not use the import statement above.
# Instead, replace the import statement with the entire code snippet from the throttler.py file.

@dataclass
class _TimeDoctorThrottlerDefaultsBase:
    """Default values for the TimeDoctorThrottler class."""
    max_requests_in_window: int = 1000 # requests per window
    rate_limit_window: int = 60 # in seconds
    throttle_start_percentage: float = 0.75 # Start throttling at 75% of the limit
    full_throttle_percentage: float = 0.90 # Fully throttle at 90% of the limit

@dataclass
class TimeDoctorThrottler(_TimeDoctorThrottlerDefaultsBase, RequestThrottler):
    """
    A specialized throttler for Time Doctor API requests that handles multiple API keys and dynamically
    adjusts rate limits based on the rate-limit headers returned by Time Doctor.
    """
    api_key: str = field(init=False, default="")
    throttle_trigger_count: int = field(init=False)
    full_throttle_trigger_count: int = field(init=False)
    request_timestamps: deque = field(default_factory=deque, init=False)
    total_requests_made: int = field(default=0, init=False)
    window_start_time: float = field(default_factory=time.time, init=False)
    request_position: int = field(default=0, init=False)
    is_server_providing_request_position: bool = field(default=False, init=False)
    is_leaky_bucket: bool = field(default=True, init=False)

    def __post_init__(self):
        """Initialize the API key after the class is instantiated."""
        self.api_key = self._get_api_key()
        self._recalculate_throttle_thresholds()

    def _recalculate_throttle_thresholds(self):
        """Recalculate the throttle and full throttle trigger counts based on the current rate limits."""
        self.throttle_trigger_count = math.ceil(self.max_requests_in_window * self.throttle_start_percentage)
        self.full_throttle_trigger_count = math.ceil(self.max_requests_in_window * self.full_throttle_percentage)

    def _get_api_key(self):
        """Get the API key from the Time Doctor API."""
        url = "https://api2.timedoctor.com/api/1.0/login"
        payload = {
            "email": "bryce.gabehart@myamazonguy.com",
            "password": "Gabehart01!",
            "permissions": "write"
        }
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        response_json = response.json()
        return response_json['data']['token']


    def _make_request(self, method, url, headers=None, params=None, data=None, json=None, retries=3, backoff_factor=2):
        """Make a request with retries using exponential backoff and jitter."""
        headers = headers or {}
        params = params or {}
        data = data or {}
        json = json or {}
    
        method_map = {
            'GET': requests.get,
            'POST': requests.post,
            'PUT': requests.put,
            'PATCH': requests.patch,
            'DELETE': requests.delete
        }
    
        if method not in method_map:
            raise ValueError("Unsupported HTTP method")
        
        # Add url parameters needed for Time Doctor
        params['token'] = self.api_key


    
        for attempt in range(retries):
            self._throttle()
    
            # Make the request
            try:
                response = method_map[method](url, headers=headers, params=params, data=data)
                print(f"[RateLimit] Request max position in window: {self.max_requests_in_window}")
                print(f"[RateLimit] Request remaining position in window: {self.max_requests_in_window - self.request_position}")
                print(f"\033[94m[RateLimit] Request position in window: {self.request_position}\033[0m")
                response.raise_for_status()
                self._record_request()
                return response
    
            # Handle HTTP errors
            except requests.exceptions.HTTPError as http_err:
                print(f"HTTPError: {http_err}")
                if not self._is_transient_error(http_err.response.status_code, http_err.response):
                    raise

                if 'Retry-After' in http_err.response.headers:
                    retry_after = int(http_err.response.headers['Retry-After'])
                    time.sleep(retry_after)
                elif attempt < retries:
                    sleep_time = (backoff_factor ** (attempt + 1)) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                else:
                    raise
    
            except requests.exceptions.RequestException as req_err:
                print(f"RequestException: {req_err}")
                if attempt < retries:
                    sleep_time = (backoff_factor ** attempt + 1) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                else:
                    raise
