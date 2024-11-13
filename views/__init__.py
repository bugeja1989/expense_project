from .dashboard_views import (
    dashboard,
    dashboard_widget,
    quick_metrics
)

from .invoice_views import (
    invoice_list,
    invoice_create,
    invoice_update,
    invoice_detail,
    invoice_send,
    invoice_void,
    invoice_pdf,
    invoice_copy,
    invoice_bulk_action,
    invoice_recurring_preview
)

from .expense_views import (
    expense_list,
    expense_create,
    expense_update,
    expense_detail,
    expense_approve,
    expense_bulk_upload,
    expense_export,
    expense_category_manage
)

from .client_views import (
    client_list,
    client_create,
    client_update,
    client_detail,
    client_statement,
    client_bulk_upload,
    client_add_note,
    client_export,
    client_credit_check
)

from .report_views import (
    report_dashboard,
    profit_loss_report,
    cash_flow_report,
    tax_report,
    aging_report,
    sales_tax_report,
    report_preview,
    export_report
)

from .user_views import (
    profile_view,
    notification_preferences,
    two_factor_setup,
    account_deletion,
    user_activity,
    user_dashboard
)

# Error handlers
def error_404(request, exception):
    """404 error handler."""
    return render(request, 'financial_app/errors/404.html', status=404)

def error_500(request):
    """500 error handler."""
    return render(request, 'financial_app/errors/500.html', status=500)

def error_403(request, exception):
    """403 error handler."""
    return render(request, 'financial_app/errors/403.html', status=403)

def error_400(request, exception):
    """400 error handler."""
    return render(request, 'financial_app/errors/400.html', status=400)

# Decorator for view logging
from functools import wraps
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def log_view_access(view_func):
    """
    Decorator to log view access and execution time.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        start_time = timezone.now()
        user_id = request.user.id if request.user.is_authenticated else None
        view_name = view_func.__name__

        try:
            response = view_func(request, *args, **kwargs)
            execution_time = (timezone.now() - start_time).total_seconds()
            
            # Log successful access
            logger.info(
                f"View accessed - View: {view_name}, User: {user_id}, "
                f"Time: {execution_time:.2f}s, Status: {response.status_code}"
            )
            
            return response
            
        except Exception as e:
            # Log error
            logger.error(
                f"View error - View: {view_name}, User: {user_id}, "
                f"Error: {str(e)}"
            )
            raise

    return wrapper

# View mixins
class ViewPermissionMixin:
    """
    Mixin to handle view permissions.
    """
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
            
        if self.required_permission and not request.user.has_perm(self.required_permission):
            raise PermissionDenied
            
        return super().dispatch(request, *args, **kwargs)

class CompanyRequiredMixin:
    """
    Mixin to ensure user has an associated company.
    """
    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'company'):
            return redirect('company_setup')
            
        return super().dispatch(request, *args, **kwargs)

# Common view utilities
def get_date_range(request):
    """
    Get date range from request parameters or default to current month.
    """
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not (start_date and end_date):
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    
    return start_date, end_date

def paginate_queryset(queryset, request, per_page=25):
    """
    Helper function to paginate querysets.
    """
    paginator = Paginator(queryset, per_page)
    page = request.GET.get('page')
    return paginator.get_page(page)

def handle_uploaded_file(uploaded_file, user):
    """
    Helper function to handle file uploads.
    """
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    import os

    # Generate unique filename
    filename = f"{user.id}_{timezone.now().timestamp()}_{uploaded_file.name}"
    path = default_storage.save(
        os.path.join('uploads', filename),
        ContentFile(uploaded_file.read())
    )
    return path

__all__ = [
    # Dashboard views
    'dashboard',
    'dashboard_widget',
    'quick_metrics',
    
    # Invoice views
    'invoice_list',
    'invoice_create',
    'invoice_update',
    'invoice_detail',
    'invoice_send',
    'invoice_void',
    'invoice_pdf',
    'invoice_copy',
    'invoice_bulk_action',
    'invoice_recurring_preview',
    
    # Expense views
    'expense_list',
    'expense_create',
    'expense_update',
    'expense_detail',
    'expense_approve',
    'expense_bulk_upload',
    'expense_export',
    'expense_category_manage',
    
    # Client views
    'client_list',
    'client_create',
    'client_update',
    'client_detail',
    'client_statement',
    'client_bulk_upload',
    'client_add_note',
    'client_export',
    'client_credit_check',
    
    # Report views
    'report_dashboard',
    'profit_loss_report',
    'cash_flow_report',
    'tax_report',
    'aging_report',
    'sales_tax_report',
    'report_preview',
    'export_report',
    
    # User views
    'profile_view',
    'notification_preferences',
    'two_factor_setup',
    'account_deletion',
    'user_activity',
    'user_dashboard',
    
    # Error handlers
    'error_404',
    'error_500',
    'error_403',
    'error_400',
]