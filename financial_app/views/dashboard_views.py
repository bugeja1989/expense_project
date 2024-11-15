# File: financial_app/views/dashboard_views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
from django.http import JsonResponse
from ..services.analytics_service import AnalyticsService
from ..models import Company

@login_required
def dashboard(request):
    """Main dashboard view combining all analytics"""
    company = request.user.company
    
    context = {
        'overview': AnalyticsService.get_business_overview(company),
        'recent_transactions': AnalyticsService.get_recent_transactions(company),
        'expense_breakdown': AnalyticsService.get_expense_breakdown(company),
        'cash_flow': AnalyticsService.get_cash_flow_trend(company),
        'payment_stats': AnalyticsService.get_payment_statistics(company)
    }
    
    return render(request, 'financial_app/dashboard/index.html', context)

@login_required
def dashboard_api_overview(request):
    """API endpoint for dashboard overview data"""
    company = request.user.company
    timeframe = request.GET.get('timeframe', 'month')
    
    overview = AnalyticsService.get_business_overview(company)
    return JsonResponse(overview)

@login_required
def dashboard_api_transactions(request):
    """API endpoint for recent transactions"""
    company = request.user.company
    limit = int(request.GET.get('limit', 10))
    
    transactions = AnalyticsService.get_recent_transactions(company, limit=limit)
    return JsonResponse({'transactions': list(transactions)})

@login_required
def dashboard_api_expenses(request):
    """API endpoint for expense breakdown"""
    company = request.user.company
    
    # Parse date range if provided
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    try:
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    expenses = AnalyticsService.get_expense_breakdown(
        company, 
        start_date=start_date, 
        end_date=end_date
    )
    return JsonResponse({'expenses': expenses})

@login_required
def dashboard_api_cash_flow(request):
    """API endpoint for cash flow trend"""
    company = request.user.company
    months = int(request.GET.get('months', 6))
    
    cash_flow = AnalyticsService.get_cash_flow_trend(company, months=months)
    return JsonResponse({'cash_flow': cash_flow})
    