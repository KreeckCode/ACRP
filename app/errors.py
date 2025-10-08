import logging
import traceback
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from functools import wraps

from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.views.decorators.cache import never_cache
from django.utils import timezone

# Import error tracking services (install via pip)
try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# Configure structured logging
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

class ErrorHandlerConfig:
    """
    Centralized configuration for error handling behavior.
    
    This class manages all configurable aspects of error handling,
    making it easy to adjust behavior across environments.
    """
    
    # Error page rate limiting (prevent abuse/DDoS)
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_REQUESTS = 10  # Max requests per window
    RATE_LIMIT_WINDOW = 60    # Window in seconds
    
    # Error tracking and monitoring
    ENABLE_SENTRY = getattr(settings, 'SENTRY_ENABLED', SENTRY_AVAILABLE)
    ENABLE_DATABASE_LOGGING = getattr(settings, 'ERROR_DB_LOGGING', True)
    ENABLE_EMAIL_ALERTS = getattr(settings, 'ERROR_EMAIL_ALERTS', not settings.DEBUG)
    
    # Response behavior
    SHOW_DEBUG_INFO = settings.DEBUG
    SHOW_STACK_TRACES = settings.DEBUG
    INCLUDE_REQUEST_HEADERS = settings.DEBUG
    
    # Security settings
    SANITIZE_SENSITIVE_DATA = True
    SENSITIVE_KEYS = [
        'password', 'secret', 'api_key', 'token', 'authorization',
        'cookie', 'session', 'csrf', 'private_key'
    ]
    
    # Performance monitoring
    LOG_SLOW_ERRORS = True
    SLOW_ERROR_THRESHOLD = 1.0  # Seconds


# ============================================================================
# CUSTOM EXCEPTION CLASSES
# ============================================================================

class BaseApplicationError(Exception):
    """
    Base exception class for all application-specific errors.
    
    Provides structured error information and consistent handling
    across the application.
    """
    
    def __init__(
        self, 
        message: str,
        error_code: str = None,
        status_code: int = 500,
        user_message: str = None,
        context: Dict[str, Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.status_code = status_code
        self.user_message = user_message or message
        self.context = context or {}
        self.timestamp = timezone.now()


class ResourceNotFoundError(BaseApplicationError):
    """Raised when a requested resource doesn't exist."""
    
    def __init__(self, resource_type: str, identifier: str, **kwargs):
        message = f"{resource_type} with identifier '{identifier}' not found"
        super().__init__(
            message=message,
            error_code='RESOURCE_NOT_FOUND',
            status_code=404,
            user_message=f"The {resource_type.lower()} you're looking for doesn't exist.",
            **kwargs
        )


class InsufficientPermissionsError(BaseApplicationError):
    """Raised when user lacks required permissions."""
    
    def __init__(self, required_permission: str, **kwargs):
        message = f"Permission denied: requires '{required_permission}'"
        super().__init__(
            message=message,
            error_code='INSUFFICIENT_PERMISSIONS',
            status_code=403,
            user_message="You don't have permission to perform this action.",
            **kwargs
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_error_id(request: HttpRequest, error: Exception) -> str:
    """
    Generate a unique, reproducible error ID for tracking.
    
    This ID allows users to reference specific errors when contacting support,
    and helps correlate error instances in logs and monitoring systems.
    
    Args:
        request: The HTTP request that triggered the error
        error: The exception that was raised
        
    Returns:
        A unique 16-character hexadecimal error ID
    """
    timestamp = datetime.now().isoformat()
    path = request.path
    error_type = type(error).__name__
    
    # Create deterministic hash from error context
    hash_input = f"{timestamp}:{path}:{error_type}:{str(error)}"
    error_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    
    return error_hash[:16].upper()


def sanitize_data(data: Any, depth: int = 0, max_depth: int = 5) -> Any:
    """
    Recursively sanitize sensitive data from dictionaries and objects.
    
    Prevents accidental exposure of passwords, tokens, and other sensitive
    information in error logs and responses. Uses a whitelist approach for
    known sensitive key patterns.
    
    Args:
        data: Data structure to sanitize (dict, list, or primitive)
        depth: Current recursion depth (internal use)
        max_depth: Maximum recursion depth to prevent infinite loops
        
    Returns:
        Sanitized copy of the input data
    """
    if depth > max_depth:
        return "[MAX_DEPTH_EXCEEDED]"
    
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Check if key contains sensitive patterns
            key_lower = str(key).lower()
            is_sensitive = any(
                sensitive in key_lower 
                for sensitive in ErrorHandlerConfig.SENSITIVE_KEYS
            )
            
            if is_sensitive:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_data(value, depth + 1, max_depth)
        return sanitized
    
    elif isinstance(data, (list, tuple)):
        return [sanitize_data(item, depth + 1, max_depth) for item in data]
    
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    
    else:
        # For unknown types, convert to string representation
        return str(data)


def capture_request_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Extract comprehensive context from the request for debugging.
    
    Captures all relevant request information while respecting security
    and privacy constraints. This data is invaluable for reproducing
    and diagnosing errors.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Dictionary containing sanitized request context
    """
    context = {
        'method': request.method,
        'path': request.path,
        'full_path': request.get_full_path(),
        'scheme': request.scheme,
        'user': {
            'id': getattr(request.user, 'id', None),
            'username': getattr(request.user, 'username', 'anonymous'),
            'is_authenticated': request.user.is_authenticated,
            'is_staff': getattr(request.user, 'is_staff', False),
        },
        'session': {
            'session_key': request.session.session_key if hasattr(request, 'session') else None,
            'exists': hasattr(request, 'session'),
        },
        'client': {
            'ip': get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
            'referrer': request.META.get('HTTP_REFERER', None),
        },
        'query_params': dict(request.GET.items()),
        'timestamp': timezone.now().isoformat(),
    }
    
    # Include headers only if configured (DEBUG mode)
    if ErrorHandlerConfig.INCLUDE_REQUEST_HEADERS:
        context['headers'] = {
            k: v for k, v in request.META.items()
            if k.startswith('HTTP_')
        }
    
    # Sanitize sensitive data
    if ErrorHandlerConfig.SANITIZE_SENSITIVE_DATA:
        context = sanitize_data(context)
    
    return context


def get_client_ip(request: HttpRequest) -> str:
    """
    Extract the real client IP address, accounting for proxies.
    
    Checks X-Forwarded-For and X-Real-IP headers to handle reverse
    proxies and CDNs correctly.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Client IP address as a string
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP in the chain (actual client)
        return x_forwarded_for.split(',')[0].strip()
    
    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip.strip()
    
    return request.META.get('REMOTE_ADDR', 'unknown')


def check_rate_limit(request: HttpRequest, error_code: str) -> Tuple[bool, int]:
    """
    Implement rate limiting for error pages to prevent abuse.
    
    Uses Django's cache framework to track error page requests per IP.
    This prevents attackers from overwhelming the system by triggering
    errors repeatedly.
    
    Args:
        request: The HTTP request object
        error_code: The error code being handled
        
    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    if not ErrorHandlerConfig.RATE_LIMIT_ENABLED:
        return True, ErrorHandlerConfig.RATE_LIMIT_REQUESTS
    
    client_ip = get_client_ip(request)
    cache_key = f"error_rate_limit:{error_code}:{client_ip}"
    
    # Get current request count
    request_count = cache.get(cache_key, 0)
    
    if request_count >= ErrorHandlerConfig.RATE_LIMIT_REQUESTS:
        return False, 0
    
    # Increment counter
    cache.set(
        cache_key,
        request_count + 1,
        ErrorHandlerConfig.RATE_LIMIT_WINDOW
    )
    
    remaining = ErrorHandlerConfig.RATE_LIMIT_REQUESTS - request_count - 1
    return True, remaining


def log_error_to_monitoring(
    error: Exception,
    request: HttpRequest,
    error_id: str,
    context: Dict[str, Any]
) -> None:
    """
    Send error information to external monitoring services.
    
    Integrates with services like Sentry, Rollbar, or custom logging
    infrastructure. Includes full context for debugging while respecting
    security constraints.
    
    Args:
        error: The exception that occurred
        request: The HTTP request object
        error_id: Unique identifier for this error instance
        context: Additional context information
    """
    # Log to Sentry if available and enabled
    if ErrorHandlerConfig.ENABLE_SENTRY and SENTRY_AVAILABLE:
        with sentry_sdk.push_scope() as scope:
            # Add custom context
            scope.set_context("error_details", {
                "error_id": error_id,
                "error_type": type(error).__name__,
            })
            scope.set_context("request_context", context)
            
            # Set user context
            if request.user.is_authenticated:
                scope.set_user({
                    "id": request.user.id,
                    "username": request.user.username,
                })
            
            # Capture the exception
            sentry_sdk.capture_exception(error)
    
    # Log to structured logger
    logger.error(
        f"Error {error_id}: {type(error).__name__}",
        extra={
            'error_id': error_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'request_context': context,
            'stack_trace': traceback.format_exc() if ErrorHandlerConfig.SHOW_STACK_TRACES else None,
        },
        exc_info=True
    )


def is_api_request(request: HttpRequest) -> bool:
    """
    Determine if the request expects a JSON response.
    
    Checks Accept headers and URL patterns to decide whether to return
    JSON (for API clients) or HTML (for browsers).
    
    Args:
        request: The HTTP request object
        
    Returns:
        True if the request expects JSON, False otherwise
    """
    # Check Accept header
    accept = request.META.get('HTTP_ACCEPT', '')
    if 'application/json' in accept:
        return True
    
    # Check if path starts with /api/
    if request.path.startswith('/api/'):
        return True
    
    # Check for explicit JSON format parameter
    if request.GET.get('format') == 'json':
        return True
    
    return False


# ============================================================================
# DECORATOR FOR ERROR HANDLING
# ============================================================================

def enhanced_error_handler(error_code: str):
    """
    Decorator that adds advanced error handling to view functions.
    
    This decorator wraps error handlers with additional functionality like
    rate limiting, logging, monitoring, and format detection.
    
    Usage:
        @enhanced_error_handler('404')
        def error_404(request, exception):
            # Your error handling logic
            pass
    
    Args:
        error_code: The HTTP error code being handled
        
    Returns:
        Decorated function with enhanced error handling
    """
    def decorator(func):
        @wraps(func)
        @never_cache  # Prevent caching of error pages
        def wrapper(request, *args, **kwargs):
            start_time = timezone.now()
            
            # Check rate limit
            is_allowed, remaining = check_rate_limit(request, error_code)
            if not is_allowed:
                logger.warning(
                    f"Rate limit exceeded for error {error_code} from {get_client_ip(request)}"
                )
                return render(
                    request,
                    'app/rate_limit.html',
                    {'error_code': '429'},
                    status=429
                )
            
            # Execute the original error handler
            response = func(request, *args, **kwargs)
            
            # Calculate execution time
            execution_time = (timezone.now() - start_time).total_seconds()
            
            # Log slow error handlers
            if (ErrorHandlerConfig.LOG_SLOW_ERRORS and 
                execution_time > ErrorHandlerConfig.SLOW_ERROR_THRESHOLD):
                logger.warning(
                    f"Slow error handler for {error_code}: {execution_time:.2f}s"
                )
            
            return response
        
        return wrapper
    return decorator


# ============================================================================
# ERROR RESPONSE BUILDERS
# ============================================================================

def build_error_context(
    request: HttpRequest,
    error: Exception,
    error_code: str,
    error_message: str,
    suggestions: list = None
) -> Dict[str, Any]:
    """
    Build comprehensive context dictionary for error templates.
    
    Creates a rich context object that includes all necessary information
    for rendering error pages, including technical details, user guidance,
    and debugging information.
    
    Args:
        request: The HTTP request object
        error: The exception that occurred
        error_code: HTTP status code
        error_message: User-friendly error message
        suggestions: List of suggested actions/links
        
    Returns:
        Dictionary of template context variables
    """
    # Generate unique error ID
    error_id = generate_error_id(request, error)
    
    # Capture request context
    request_context = capture_request_context(request)
    
    # Log to monitoring services
    log_error_to_monitoring(error, request, error_id, request_context)
    
    # Build base context
    context = {
        'error_code': error_code,
        'error_message': error_message,
        'request_id': error_id,
        'suggestions': suggestions or [],
        'debug': settings.DEBUG,
        'version': getattr(settings, 'VERSION', 'dev'),
    }
    
    # Add debug information if enabled
    if ErrorHandlerConfig.SHOW_DEBUG_INFO:
        context['error_debug'] = {
            'exception_type': type(error).__name__,
            'exception_message': str(error),
            'request_context': request_context,
        }
        
        if ErrorHandlerConfig.SHOW_STACK_TRACES:
            context['error_debug']['stack_trace'] = traceback.format_exc()
    
    # Add custom exception context if available
    if isinstance(error, BaseApplicationError):
        context['error_context'] = error.context
    
    return context


def build_json_error_response(
    request: HttpRequest,
    error: Exception,
    error_code: str,
    error_message: str,
    status_code: int
) -> JsonResponse:
    """
    Build standardized JSON error response for API requests.
    
    Returns errors in a consistent format that API clients can parse
    and handle programmatically.
    
    Args:
        request: The HTTP request object
        error: The exception that occurred
        error_code: Error code/type
        error_message: Human-readable error message
        status_code: HTTP status code
        
    Returns:
        JsonResponse with error details
    """
    error_id = generate_error_id(request, error)
    request_context = capture_request_context(request)
    
    # Log to monitoring
    log_error_to_monitoring(error, request, error_id, request_context)
    
    response_data = {
        'error': {
            'code': error_code,
            'message': error_message,
            'request_id': error_id,
            'timestamp': timezone.now().isoformat(),
        },
        'status': status_code,
    }
    
    # Add debug info if enabled
    if ErrorHandlerConfig.SHOW_DEBUG_INFO:
        response_data['debug'] = {
            'exception_type': type(error).__name__,
            'exception_message': str(error),
            'path': request.path,
        }
        
        if ErrorHandlerConfig.SHOW_STACK_TRACES:
            response_data['debug']['stack_trace'] = traceback.format_tb(
                error.__traceback__
            )
    
    return JsonResponse(response_data, status=status_code)


# ============================================================================
# ADVANCED ERROR HANDLERS
# ============================================================================

@enhanced_error_handler('404')
def error_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Advanced 404 Not Found handler with intelligent suggestions.
    
    Provides context-aware navigation suggestions based on the request path
    and user permissions. Logs 404s for analytics and broken link detection.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 404
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'The page you are looking for could not be found.'
    
    # Build intelligent suggestions based on context
    suggestions = []
    
    # Always offer dashboard for authenticated users
    if request.user.is_authenticated:
        suggestions.append(('Dashboard', '/app/dashboard/'))
    
    # Suggest similar resources based on path
    path_parts = request.path.strip('/').split('/')
    if 'project' in path_parts:
        suggestions.extend([
            ('All Projects', '/app/projects/'),
            ('My Projects', '/app/projects/?filter=my'),
        ])
    elif 'task' in path_parts:
        suggestions.extend([
            ('All Tasks', '/app/tasks/'),
            ('Kanban Board', '/app/kanban/'),
        ])
    
    # Add search option
    suggestions.append(('Search', f'/app/search/?q={path_parts[-1] if path_parts else ""}'))
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '404', error_message, 404
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '404', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=404)


@enhanced_error_handler('500')
def error_500(request: HttpRequest) -> HttpResponse:
    """
    Advanced 500 Internal Server Error handler with incident tracking.
    
    Captures full diagnostic information, creates incident reports,
    and notifies the development team. Provides users with a reference
    ID for support inquiries.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'An internal server error occurred. Our team has been notified.'
    
    # Create a generic exception for 500 errors without an exception object
    exception = Exception("Internal Server Error")
    
    # Suggestions for recovery
    suggestions = [
        ('Dashboard', '/app/dashboard/'),
        ('Refresh Page', request.path),
    ]
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '500', error_message, 500
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '500', error_message, suggestions
    )
    
    # Additional incident tracking
    error_id = context['request_id']
    logger.critical(
        f"500 Internal Server Error - Incident ID: {error_id}",
        extra={
            'incident_id': error_id,
            'requires_investigation': True,
            'severity': 'CRITICAL',
        }
    )
    
    return render(request, 'app/error.html', context, status=500)


@enhanced_error_handler('403')
def error_403(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Advanced 403 Forbidden handler with permission guidance.
    
    Provides detailed information about required permissions and suggests
    ways to gain access. Logs access denial attempts for security monitoring.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 403
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'You do not have permission to access this resource.'
    
    # Build context-aware suggestions
    suggestions = []
    
    if request.user.is_authenticated:
        suggestions.extend([
            ('Dashboard', '/app/dashboard/'),
            ('My Projects', '/app/projects/?filter=my'),
        ])
        
        # Suggest contacting admin if user has limited permissions
        if not request.user.is_staff:
            suggestions.append(('Request Access', '/support/access-request/'))
    else:
        # User is not authenticated - suggest login
        suggestions.extend([
            ('Login', f'/accounts/login/?next={request.path}'),
            ('Sign Up', '/accounts/signup/'),
        ])
    
    # Log security event
    logger.warning(
        f"403 Forbidden: {request.user.username if request.user.is_authenticated else 'anonymous'} "
        f"attempted to access {request.path}",
        extra={
            'security_event': True,
            'event_type': 'access_denied',
            'user_id': request.user.id if request.user.is_authenticated else None,
            'path': request.path,
            'ip_address': get_client_ip(request),
        }
    )
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '403', error_message, 403
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '403', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=403)


@enhanced_error_handler('400')
def error_400(request: HttpRequest, exception: Exception) -> HttpResponse:
    """
    Advanced 400 Bad Request handler with input validation guidance.
    
    Analyzes the request to identify validation issues and provides
    helpful feedback for fixing the problem.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 400
        
    Returns:
        Rendered error page or JSON response
    """
    error_message = 'Bad request. Please check your input and try again.'
    
    # Try to extract validation details from the exception
    if isinstance(exception, SuspiciousOperation):
        error_message = 'Your request appears to be malformed or suspicious.'
    
    suggestions = [
        ('Dashboard', '/app/dashboard/'),
        ('Help & Documentation', '/help/'),
    ]
    
    # Log suspicious requests
    if isinstance(exception, SuspiciousOperation):
        logger.warning(
            f"Suspicious operation detected: {str(exception)}",
            extra={
                'security_event': True,
                'event_type': 'suspicious_operation',
                'ip_address': get_client_ip(request),
                'path': request.path,
            }
        )
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '400', error_message, 400
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '400', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=400)


@enhanced_error_handler('401')
def error_401(request: HttpRequest, exception: Exception = None) -> HttpResponse:
    """
    Advanced 401 Unauthorized handler for authentication failures.
    
    Handles authentication failures with appropriate redirect logic
    and session management.
    
    Args:
        request: The HTTP request object
        exception: The exception that triggered the 401 (optional)
        
    Returns:
        Rendered error page or JSON response
    """
    if exception is None:
        exception = Exception("Unauthorized")
    
    error_message = 'Authentication is required to access this resource.'
    
    suggestions = [
        ('Login', f'/accounts/login/?next={request.path}'),
        ('Sign Up', '/accounts/signup/'),
        ('Forgot Password', '/accounts/password/reset/'),
    ]
    
    # Check if this is an API request
    if is_api_request(request):
        return build_json_error_response(
            request, exception, '401', error_message, 401
        )
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '401', error_message, suggestions
    )
    
    return render(request, 'app/error.html', context, status=401)


@enhanced_error_handler('429')
def error_429(request: HttpRequest) -> HttpResponse:
    """
    Advanced 429 Too Many Requests handler for rate limiting.
    
    Informs users about rate limits and when they can retry.
    
    Args:
        request: The HTTP request object
        
    Returns:
        Rendered error page or JSON response
    """
    exception = Exception("Too Many Requests")
    error_message = 'You have made too many requests. Please slow down and try again later.'
    
    # Calculate when the user can retry
    retry_after = ErrorHandlerConfig.RATE_LIMIT_WINDOW
    
    suggestions = [
        ('Dashboard', '/app/dashboard/'),
    ]
    
    # Check if this is an API request
    if is_api_request(request):
        response = build_json_error_response(
            request, exception, '429', error_message, 429
        )
        response['Retry-After'] = str(retry_after)
        return response
    
    # Build and render HTML response
    context = build_error_context(
        request, exception, '429', error_message, suggestions
    )
    context['retry_after'] = retry_after
    
    response = render(request, 'app/error.html', context, status=429)
    response['Retry-After'] = str(retry_after)
    
    return response


# ============================================================================
# MIDDLEWARE FOR GLOBAL ERROR HANDLING
# ============================================================================

class EnhancedErrorHandlingMiddleware:
    """
    Middleware that provides global error handling and monitoring.
    
    This middleware catches all unhandled exceptions and provides consistent
    error handling across the application. It should be placed near the top
    of the middleware stack.
    
    Usage:
        Add to settings.py MIDDLEWARE:
        'app.errors.EnhancedErrorHandlingMiddleware',
    """
    
    def __init__(self, get_response):
        """
        Initialize middleware.
        
        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response
    
    def __call__(self, request):
        """
        Process request and catch any unhandled exceptions.
        
        Args:
            request: The HTTP request object
            
        Returns:
            HTTP response
        """
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            # Log the exception
            logger.exception("Unhandled exception in middleware")
            
            # Return appropriate error response
            return self.process_exception(request, e)
    
    def process_exception(self, request, exception):
        """
        Handle exceptions that weren't caught by views.
        
        Args:
            request: The HTTP request object
            exception: The unhandled exception
            
        Returns:
            HTTP response
        """
        # Determine appropriate status code
        if isinstance(exception, PermissionDenied):
            return error_403(request, exception)
        elif isinstance(exception, SuspiciousOperation):
            return error_400(request, exception)
        elif isinstance(exception, BaseApplicationError):
            # Handle custom application errors
            if is_api_request(request):
                return build_json_error_response(
                    request,
                    exception,
                    exception.error_code,
                    exception.user_message,
                    exception.status_code
                )
            
            context = build_error_context(
                request,
                exception,
                str(exception.status_code),
                exception.user_message,
                []
            )
            return render(
                request,
                'app/error.html',
                context,
                status=exception.status_code
            )
        else:
            # Generic 500 error for all other exceptions
            return error_500(request)


# ============================================================================
# HEALTH CHECK & MONITORING ENDPOINTS
# ============================================================================

def health_check(request: HttpRequest) -> JsonResponse:
    """
    Health check endpoint for monitoring systems.
    
    Provides system status information for load balancers,
    monitoring services, and orchestration platforms.
    
    Returns:
        JSON response with health status
    """
    from django.db import connection
    
    status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }
    
    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status['checks']['database'] = 'ok'
    except Exception as e:
        status['status'] = 'unhealthy'
        status['checks']['database'] = f'error: {str(e)}'
    
    # Check cache connectivity
    try:
        cache.set('health_check', 'ok', 10)
        cache.get('health_check')
        status['checks']['cache'] = 'ok'
    except Exception as e:
        status['status'] = 'degraded'
        status['checks']['cache'] = f'error: {str(e)}'
    
    # Return appropriate status code
    status_code = 200 if status['status'] == 'healthy' else 503
    
    return JsonResponse(status, status=status_code)