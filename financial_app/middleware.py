from django.utils import timezone
from actstream import action
from django.contrib.contenttypes.models import ContentType

class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        if hasattr(request, 'user') and request.user.is_authenticated:
            if request.method in ['POST', 'PUT', 'DELETE']:
                # Log write operations
                action_text = f"{request.method} on {request.path}"
                action.send(request.user, verb=action_text, target=None)
        
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Log specific views if needed
        return None

    def process_exception(self, request, exception):
        if hasattr(request, 'user') and request.user.is_authenticated:
            action.send(
                request.user,
                verb="encountered error",
                description=str(exception),
                target=None
            )
        return None