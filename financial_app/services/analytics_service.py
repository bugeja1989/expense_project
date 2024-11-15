# File: financial_app/services/analytics_service.py

from django.db.models import Sum, Count, F, Value, CharField
from django.db.models.functions import TruncMonth, Coalesce
from django.utils import timezone
from datetime import timedelta
from ..models import Invoice, Expense, ExpenseCategory, PaymentRecord

class AnalyticsService:
    @staticmethod
    def get_business_overview(company):
        """
        Get comprehensive business overview including income, expenses, and trends
        """
        current_period_end = timezone.now()
        current_period_start = current_period_end - timedelta(days=30)
        previous_period_start = current_period_start - timedelta(days=30)

        # Current period metrics
        current_income = Invoice.objects.filter(
            company=company,
            issue_date__range=[current_period_start, current_period_end],
            status='PAID'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

        current_expenses = Expense.objects.filter(
            company=company,
            date__range=[current_period_start, current_period_end]
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        # Previous period metrics
        previous_income = Invoice.objects.filter(
            company=company,
            issue_date__range=[previous_period_start, current_period_start],
            status='PAID'
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 1  # Avoid division by zero

        previous_expenses = Expense.objects.filter(
            company=company,
            date__range=[previous_period_start, current_period_start]
        ).aggregate(Sum('amount'))['amount__sum'] or 1

        # Outstanding invoices
        outstanding = Invoice.objects.filter(
            company=company,
            status='SENT'
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id')
        )

        # Overdue invoices
        overdue = Invoice.objects.filter(
            company=company,
            status='SENT',
            due_date__lt=timezone.now()
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id')
        )

        return {
            'total_income': current_income,
            'total_expenses': current_expenses,
            'income_trend': ((current_income - previous_income) / previous_income) * 100,
            'expense_trend': ((current_expenses - previous_expenses) / previous_expenses) * 100,
            'outstanding_invoices': outstanding['total'] or 0,
            'pending_invoices_count': outstanding['count'] or 0,
            'overdue_invoices': overdue['total'] or 0,
            'overdue_invoices_count': overdue['count'] or 0,
            'net_cash_flow': current_income - current_expenses,
            'cash_flow_trend': (((current_income - current_expenses) - 
                               (previous_income - previous_expenses)) / 
                              abs(previous_income - previous_expenses)) * 100 if previous_income != previous_expenses else 0
        }

    @staticmethod
    def get_recent_transactions(company, limit=10):
        """
        Get recent transactions (both income and expenses) for a company
        """
        # Get recent invoices (income)
        recent_invoices = Invoice.objects.filter(
            company=company,
            status='PAID'
        ).order_by('-payment_date')[:limit].annotate(
            type=Value('income', output_field=CharField()),
            description=F('client__name'),
            date=F('payment_date'),
            reference=F('invoice_number')
        ).values('type', 'description', 'date', 'reference', 'total_amount')

        # Get recent expenses
        recent_expenses = Expense.objects.filter(
            company=company
        ).order_by('-date')[:limit].annotate(
            type=Value('expense', output_field=CharField()),
            amount=F('amount'),
            reference=Value('', output_field=CharField())
        ).values('type', 'description', 'date', 'category__name', 'amount', 'reference')

        # Combine and sort transactions
        all_transactions = list(recent_invoices) + list(recent_expenses)
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        return all_transactions[:limit]

    @staticmethod
    def get_expense_breakdown(company, start_date=None, end_date=None):
        """
        Get expense breakdown by category
        """
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        categories = ExpenseCategory.objects.filter(
            expense__company=company,
            expense__date__range=[start_date, end_date]
        ).annotate(
            total_amount=Sum('expense__amount'),
            percentage=F('total_amount') * 100.0 / Sum('expense__amount'),
        ).values('name', 'total_amount', 'percentage')

        return list(categories)

    @staticmethod
    def get_cash_flow_trend(company, months=6):
        """
        Get cash flow trend over specified number of months
        """
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30 * months)

        income_by_month = Invoice.objects.filter(
            company=company,
            status='PAID',
            payment_date__range=[start_date, end_date]
        ).annotate(
            month=TruncMonth('payment_date')
        ).values('month').annotate(
            total=Sum('total_amount')
        ).order_by('month')

        expenses_by_month = Expense.objects.filter(
            company=company,
            date__range=[start_date, end_date]
        ).annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            total=Sum('amount')
        ).order_by('month')

        # Combine into cash flow trend
        trend = {}
        for income in income_by_month:
            month = income['month'].strftime('%Y-%m')
            trend[month] = {
                'income': income['total'],
                'expenses': 0,
                'net': income['total']
            }

        for expense in expenses_by_month:
            month = expense['month'].strftime('%Y-%m')
            if month not in trend:
                trend[month] = {'income': 0, 'expenses': 0, 'net': 0}
            trend[month]['expenses'] = expense['total']
            trend[month]['net'] = trend[month]['income'] - expense['total']

        return [{'month': k, **v} for k, v in sorted(trend.items())]

    @staticmethod
    def get_payment_statistics(company):
        """
        Get payment-related statistics
        """
        total_invoices = Invoice.objects.filter(company=company)
        paid_invoices = total_invoices.filter(status='PAID')
        overdue_invoices = total_invoices.filter(
            status='SENT',
            due_date__lt=timezone.now()
        )

        total_count = total_invoices.count()
        if total_count == 0:
            return {
                'payment_rate': 0,
                'average_days_to_pay': 0,
                'overdue_rate': 0
            }

        # Calculate average days to pay
        avg_days = PaymentRecord.objects.filter(
            invoice__company=company
        ).annotate(
            days_to_pay=F('payment_date') - F('invoice__issue_date')
        ).aggregate(
            avg_days=Coalesce(Sum('days_to_pay') / Count('id'), 0)
        )['avg_days']

        return {
            'payment_rate': (paid_invoices.count() / total_count) * 100,
            'average_days_to_pay': avg_days.days if hasattr(avg_days, 'days') else 0,
            'overdue_rate': (overdue_invoices.count() / total_count) * 100
        }