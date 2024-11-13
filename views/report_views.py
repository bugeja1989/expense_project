from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import json
from datetime import datetime, timedelta

from ..models import Company, Invoice, Expense, Client
from ..forms import (
    DateRangeForm, ProfitLossReportForm,
    CashFlowReportForm, TaxReportForm,
    ReportExportForm
)
from ..services.report_service import ReportService

@login_required
def report_dashboard(request):
    """
    Main reporting dashboard showing available reports and recent exports.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    # Get summary metrics
    current_year = timezone.now().year
    metrics = {
        'total_revenue': Invoice.objects.filter(
            company=company,
            status='PAID',
            issue_date__year=current_year
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        'total_expenses': Expense.objects.filter(
            company=company,
            date__year=current_year
        ).aggregate(total=Sum('amount'))['total'] or 0,
        
        'outstanding_invoices': Invoice.objects.filter(
            company=company,
            status__in=['SENT', 'OVERDUE']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
    }
    
    metrics['net_profit'] = metrics['total_revenue'] - metrics['total_expenses']
    
    context = {
        'metrics': metrics,
        'available_reports': [
            {
                'name': 'profit_loss',
                'title': _('Profit & Loss'),
                'description': _('Comprehensive P&L statement with comparisons')
            },
            {
                'name': 'cash_flow',
                'title': _('Cash Flow'),
                'description': _('Cash flow analysis with forecasting')
            },
            {
                'name': 'tax',
                'title': _('Tax Report'),
                'description': _('Tax liability and deductions summary')
            }
        ]
    }
    
    return render(request, 'financial_app/reports/dashboard.html', context)

@login_required
def profit_loss_report(request):
    """
    Generate Profit & Loss report with comparison options.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    if request.method == 'POST':
        form = ProfitLossReportForm(request.POST)
        if form.is_valid():
            try:
                report_data = ReportService.generate_pl_statement(
                    company,
                    form.cleaned_data['start_date'],
                    form.cleaned_data['end_date'],
                    compare_previous=form.cleaned_data['compare_previous'],
                    expense_categories=form.cleaned_data['expense_categories'],
                    include_draft=form.cleaned_data['include_draft_invoices']
                )
                
                if request.POST.get('export'):
                    return export_report(report_data, 'profit_loss', request.POST.get('format', 'pdf'))
                
                context = {
                    'form': form,
                    'report_data': report_data,
                    'export_form': ReportExportForm()
                }
                return render(request, 'financial_app/reports/profit_loss.html', context)
                
            except Exception as e:
                messages.error(request, str(e))
    else:
        # Initialize with current month
        today = timezone.now().date()
        form = ProfitLossReportForm(initial={
            'start_date': today.replace(day=1),
            'end_date': today
        })
    
    context = {
        'form': form,
        'export_form': ReportExportForm()
    }
    
    return render(request, 'financial_app/reports/profit_loss.html', context)

@login_required
def cash_flow_report(request):
    """
    Generate Cash Flow report with forecasting.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    if request.method == 'POST':
        form = CashFlowReportForm(request.POST)
        if form.is_valid():
            try:
                report_data = ReportService.generate_cash_flow_statement(
                    company,
                    form.cleaned_data['start_date'],
                    form.cleaned_data['end_date'],
                    include_pending=form.cleaned_data['include_pending'],
                    forecast_periods=form.cleaned_data['forecast_periods']
                )
                
                if request.POST.get('export'):
                    return export_report(report_data, 'cash_flow', request.POST.get('format', 'pdf'))
                
                context = {
                    'form': form,
                    'report_data': report_data,
                    'export_form': ReportExportForm()
                }
                return render(request, 'financial_app/reports/cash_flow.html', context)
                
            except Exception as e:
                messages.error(request, str(e))
    else:
        # Initialize with last 3 months
        today = timezone.now().date()
        form = CashFlowReportForm(initial={
            'start_date': today - timedelta(days=90),
            'end_date': today
        })
    
    context = {
        'form': form,
        'export_form': ReportExportForm()
    }
    
    return render(request, 'financial_app/reports/cash_flow.html', context)

@login_required
def tax_report(request):
    """
    Generate Tax report with deductions.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    if request.method == 'POST':
        form = TaxReportForm(request.POST)
        if form.is_valid():
            try:
                report_data = ReportService.generate_tax_report(
                    company,
                    form.cleaned_data['start_date'].year,
                    tax_rate=form.cleaned_data['tax_rate'],
                    include_tax_deductible_only=form.cleaned_data['include_tax_deductible_only']
                )
                
                if request.POST.get('export'):
                    return export_report(report_data, 'tax', request.POST.get('format', 'pdf'))
                
                context = {
                    'form': form,
                    'report_data': report_data,
                    'export_form': ReportExportForm()
                }
                return render(request, 'financial_app/reports/tax.html', context)
                
            except Exception as e:
                messages.error(request, str(e))
    else:
        # Initialize with current year
        form = TaxReportForm(initial={
            'start_date': timezone.now().date().replace(month=1, day=1),
            'end_date': timezone.now().date()
        })
    
    context = {
        'form': form,
        'export_form': ReportExportForm()
    }
    
    return render(request, 'financial_app/reports/tax.html', context)

@login_required
def aging_report(request):
    """
    Generate Accounts Receivable Aging report.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    aging_data = ReportService.get_aging_report(company)
    
    if request.GET.get('export'):
        return export_report(aging_data, 'aging', request.GET.get('format', 'pdf'))
    
    context = {
        'aging_data': aging_data,
        'export_form': ReportExportForm()
    }
    
    return render(request, 'financial_app/reports/aging.html', context)

@login_required
def sales_tax_report(request):
    """
    Generate Sales Tax report.
    """
    company = get_object_or_404(Company, owner=request.user)
    
    date_form = DateRangeForm(request.GET)
    if date_form.is_valid():
        start_date = date_form.cleaned_data['start_date']
        end_date = date_form.cleaned_data['end_date']
    else:
        # Default to current month
        today = timezone.now().date()
        start_date = today.replace(day=1)
        end_date = today
    
    tax_data = ReportService.generate_sales_tax_report(
        company,
        start_date,
        end_date
    )
    
    if request.GET.get('export'):
        return export_report(tax_data, 'sales_tax', request.GET.get('format', 'pdf'))
    
    context = {
        'date_form': date_form,
        'tax_data': tax_data,
        'export_form': ReportExportForm()
    }
    
    return render(request, 'financial_app/reports/sales_tax.html', context)

def export_report(data, report_type, format_type):
    """
    Export report data in specified format.
    """
    try:
        if format_type == 'pdf':
            response = ReportService.export_as_pdf(data, report_type)
        elif format_type == 'xlsx':
            response = ReportService.export_as_excel(data, report_type)
        elif format_type == 'csv':
            response = ReportService.export_as_csv(data, report_type)
        else:
            raise ValueError("Unsupported export format")
        
        return response
        
    except Exception as e:
        messages.error(request, str(e))
        return redirect(request.path)

@login_required
def report_preview(request):
    """
    AJAX endpoint for report preview.
    """
    company = get_object_or_404(Company, owner=request.user)
    report_type = request.GET.get('type')
    
    try:
        if report_type == 'profit_loss':
            data = ReportService.generate_pl_preview(company)
        elif report_type == 'cash_flow':
            data = ReportService.generate_cash_flow_preview(company)
        elif report_type == 'tax':
            data = ReportService.generate_tax_preview(company)
        else:
            raise ValueError("Invalid report type")
            
        return JsonResponse({'data': data})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)