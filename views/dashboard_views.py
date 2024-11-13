from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count
from django.core.cache import cache
from django.conf import settings
from datetime import timedelta, datetime
import json

from ..models import (
    Company, Invoice, Expense, Client,
    PaymentRecord
)
from ..services.analytics_service import AnalyticsService
from ..services.report_service import ReportService

@login_required
def dashboard(request):
    """
    Main dashboard view showing key metrics and recent activity.
    """
    try:
        company = request.user.company
    except Company.DoesNotExist:
        return redirect('company_setup')

    # Cache key for dashboard data
    cache_key = f'dashboard_data_{company.id}_{timezone.now().date()}'
    dashboard_data = cache.get(cache_key)

    if not dashboard_data:
        # Calculate date ranges
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Get key metrics
        metrics = {
            'total_revenue': get_revenue_metrics(company, start_of_month, end_of_month),
            'total_expenses': get_expense_metrics(company, start_of_month, end_of_month),
            'outstanding_invoices': get_invoice_metrics(company),
            'client_stats': get_client_metrics(company)
        }

        # Get recent activity
        activity = {
            'recent_invoices': get_recent_invoices(company),
            'recent_expenses': get_recent_expenses(company),
            'recent_payments': get_recent_payments(company)
        }

        # Get charts data
        charts = {
            'revenue_trend': get_revenue_trend(company),
            'expense_categories': get_expense_breakdown(company),
            'cash_flow': get_cash_flow_data(company)
        }

        dashboard_data = {
            'metrics': metrics,
            'activity': activity,
            'charts': charts
        }

        # Cache the dashboard data for 1 hour
        cache.set(cache_key, dashboard_data, 3600)

    context = {
        'dashboard_data': dashboard_data,
        'company': company
    }

    return render(request, 'financial_app/dashboard/index.html', context)

def get_revenue_metrics(company, start_date, end_date):
    """Calculate revenue metrics for the dashboard."""
    return {
        'current_month': Invoice.objects.filter(
            company=company,
            status='PAID',
            issue_date__range=[start_date, end_date]
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        'overdue_amount': Invoice.objects.filter(
            company=company,
            status='OVERDUE'
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        'pending_amount': Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'PARTIALLY_PAID']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
    }

def get_expense_metrics(company, start_date, end_date):
    """Calculate expense metrics for the dashboard."""
    return {
        'current_month': Expense.objects.filter(
            company=company,
            date__range=[start_date, end_date]
        ).aggregate(total=Sum('amount'))['total'] or 0,
        
        'pending_approval': Expense.objects.filter(
            company=company,
            approved_by__isnull=True
        ).count(),
        
        'by_category': Expense.objects.filter(
            company=company,
            date__range=[start_date, end_date]
        ).values('category__name').annotate(
            total=Sum('amount')
        ).order_by('-total')[:5]
    }

def get_invoice_metrics(company):
    """Calculate invoice metrics for the dashboard."""
    return {
        'total_outstanding': Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'OVERDUE', 'PARTIALLY_PAID']
        ).count(),
        
        'overdue_count': Invoice.objects.filter(
            company=company,
            status='OVERDUE'
        ).count(),
        
        'draft_count': Invoice.objects.filter(
            company=company,
            status='DRAFT'
        ).count()
    }

def get_client_metrics(company):
    """Calculate client metrics for the dashboard."""
    return {
        'total_active': Client.objects.filter(
            company=company,
            is_active=True
        ).count(),
        
        'new_this_month': Client.objects.filter(
            company=company,
            created_at__month=timezone.now().month
        ).count(),
        
        'with_overdue': Client.objects.filter(
            company=company,
            invoices__status='OVERDUE'
        ).distinct().count()
    }

def get_recent_invoices(company, limit=5):
    """Get recent invoices for the dashboard."""
    return Invoice.objects.filter(
        company=company
    ).select_related('client').order_by(
        '-created_at'
    )[:limit].values(
        'id', 'invoice_number', 'client__name',
        'total_amount', 'status', 'due_date'
    )

def get_recent_expenses(company, limit=5):
    """Get recent expenses for the dashboard."""
    return Expense.objects.filter(
        company=company
    ).select_related('category').order_by(
        '-created_at'
    )[:limit].values(
        'id', 'category__name', 'amount',
        'date', 'vendor'
    )

def get_recent_payments(company, limit=5):
    """Get recent payments for the dashboard."""
    return PaymentRecord.objects.filter(
        invoice__company=company
    ).select_related('invoice').order_by(
        '-created_at'
    )[:limit].values(
        'id', 'invoice__invoice_number',
        'amount', 'payment_date', 'payment_method'
    )

def get_revenue_trend(company):
    """Generate revenue trend data for charts."""
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=180)
    
    return AnalyticsService.get_revenue_trend(
        company,
        start_date,
        end_date
    )

def get_expense_breakdown(company):
    """Generate expense breakdown data for charts."""
    return AnalyticsService.get_expense_breakdown(
        company,
        timezone.now().date().replace(day=1)
    )

def get_cash_flow_data(company):
    """Generate cash flow data for charts."""
    return AnalyticsService.get_cash_flow_data(
        company,
        timezone.now().date() - timedelta(days=90),
        timezone.now().date() + timedelta(days=30)
    )

@login_required
def dashboard_widget(request, widget_name):
    """AJAX endpoint for updating individual dashboard widgets."""
    try:
        company = request.user.company
        
        widget_functions = {
            'revenue_metrics': get_revenue_metrics,
            'expense_metrics': get_expense_metrics,
            'invoice_metrics': get_invoice_metrics,
            'client_metrics': get_client_metrics,
            'recent_invoices': get_recent_invoices,
            'recent_expenses': get_recent_expenses,
            'recent_payments': get_recent_payments,
            'revenue_trend': get_revenue_trend,
            'expense_breakdown': get_expense_breakdown,
            'cash_flow': get_cash_flow_data
        }

        if widget_name not in widget_functions:
            return JsonResponse({'error': 'Invalid widget name'}, status=400)

        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        data = widget_functions[widget_name](company, start_of_month, end_of_month)
        return JsonResponse({'data': data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def quick_metrics(request):
    """AJAX endpoint for quick metrics panel."""
    try:
        company = request.user.company
        today = timezone.now().date()
        
        metrics = {
            'invoices_due_today': Invoice.objects.filter(
                company=company,
                due_date=today,
                status__in=['SENT', 'PARTIALLY_PAID']
            ).count(),
            
            'payments_received_today': PaymentRecord.objects.filter(
                invoice__company=company,
                payment_date=today,
                status='COMPLETED'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            
            'expenses_today': Expense.objects.filter(
                company=company,
                date=today
            ).aggregate(total=Sum('amount'))['total'] or 0,
            
            'pending_approvals': Expense.objects.filter(
                company=company,
                approved_by__isnull=True
            ).count()
        }
        
        return JsonResponse(metrics)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)