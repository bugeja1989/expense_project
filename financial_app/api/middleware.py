from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import APIException
import jwt
import json
import logging
import traceback
from ..models import UserProfile

logger = logging.getLogger(__name__)

class APILoggingMiddleware:
    """
    Middleware to log all API requests and responses
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip logging for non-API requests
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        # Log request
        start_time = timezone.now()
        method = request.method
        path = request.path
        query_params = dict(request.GET)
        headers = self.get_safe_headers(request)

        # Log request body for non-GET requests
        body = None
        if method != 'GET':
            try:
                body = json.loads(request.body) if request.body else None
            except json.JSONDecodeError:
                body = '<Invalid JSON>'

        # Get the response
        response = self.get_response(request)

        # Calculate request duration
        duration = (timezone.now() - start_time).total_seconds()

        # Log response
        status_code = response.status_code
        response_body = None

        if status_code != 204:  # No content
            try:
                response_body = json.loads(response.content)
            except json.JSONDecodeError:
                response_body = '<Invalid JSON>'

        # Prepare log entry
        log_entry = {
            'timestamp': start_time.isoformat(),
            'method': method,
            'path': path,
            'query_params': query_params,
            'headers': headers,
            'request_body': body,
            'status_code': status_code,
            'response_body': response_body,
            'duration': duration,
            'user_id': request.user.id if request.user.is_authenticated else None,
        }

        # Log based on status code
        if status_code >= 500:
            logger.error(json.dumps(log_entry))
        elif status_code >= 400:
            logger.warning(json.dumps(log_entry))
        else:
            logger.info(json.dumps(log_entry))

        return response

    def get_safe_headers(self, request):
        """
        Get headers safe for logging (exclude sensitive information)
        """
        sensitive_headers = {'authorization', 'cookie', 'x-csrftoken'}
        return {
            k.lower(): v for k, v in request.headers.items()
            if k.lower() not in sensitive_headers
        }

class RateLimitMiddleware:
    """
    Middleware to implement rate limiting
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limits = {
            'DEFAULT': {'calls': 100, 'period': 60},  # 100 calls per minute
            'EXPORT': {'calls': 10, 'period': 3600},  # 10 exports per hour
        }

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        if not request.user.is_authenticated:
            return self.get_response(request)

        # Determine rate limit type
        limit_type = 'EXPORT' if '/export/' in request.path else 'DEFAULT'
        
        # Check rate limit
        if self.is_rate_limited(request, limit_type):
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'detail': f'Please try again later'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        return self.get_response(request)

    def is_rate_limited(self, request, limit_type):
        from django.core.cache import cache
        
        key = f"rate_limit:{request.user.id}:{limit_type}:{timezone.now().strftime('%Y%m%d%H%M')}"
        current = cache.get(key, 0)
        
        if current >= self.rate_limits[limit_type]['calls']:
            return True
        
        cache.set(
            key,
            current + 1,
            self.rate_limits[limit_type]['period']
        )
        return False

class JWTAuthenticationMiddleware:
    """
    Middleware to handle JWT authentication
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=['HS256']
                )
                request.user_token_payload = payload
            except jwt.ExpiredSignatureError:
                return JsonResponse({
                    'error': 'Token expired',
                    'detail': 'Please refresh your token'
                }, status=status.HTTP_401_UNAUTHORIZED)
            except jwt.InvalidTokenError:
                return JsonResponse({
                    'error': 'Invalid token',
                    'detail': 'Token validation failed'
                }, status=status.HTTP_401_UNAUTHORIZED)

        return self.get_response(request)

class ErrorHandlingMiddleware:
    """
    Middleware to handle all API errors consistently
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            return self.handle_exception(e, request)

    def handle_exception(self, exc, request):
        if not request.path.startswith('/api/'):
            raise exc

        # Log the full exception
        logger.error(f"API Error: {str(exc)}\n{traceback.format_exc()}")

        if isinstance(exc, APIException):
            # Handle DRF exceptions
            return JsonResponse({
                'error': exc.__class__.__name__,
                'detail': str(exc)
            }, status=exc.status_code)

        # Handle other exceptions
        return JsonResponse({
            'error': 'Internal Server Error',
            'detail': str(exc) if settings.DEBUG else 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserActivityMiddleware:
    """
    Middleware to track user activity
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            try:
                profile = UserProfile.objects.get(user=request.user)
                profile.last_active = timezone.now()
                profile.last_login_ip = self.get_client_ip(request)
                profile.save(update_fields=['last_active', 'last_login_ip'])
            except UserProfile.DoesNotExist:
                pass

        return response

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')

class TimeZoneMiddleware:
    """
    Middleware to handle user timezone preferences
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
                if profile.timezone:
                    timezone.activate(profile.timezone)
            except UserProfile.DoesNotExist:
                pass

        return self.get_response(request)