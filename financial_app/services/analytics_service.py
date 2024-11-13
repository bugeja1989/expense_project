from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Avg, F, Q, Window
from django.db.models.functions import TruncMonth, TruncYear, ExtractYear, Lag
import pandas as pd
import numpy as np
from datetime import timedelta
import logging
from ..models import Invoice, Expense, Client, PaymentRecord

logger = logging.getLogger(__name__)

class AnalyticsService:
    @staticmethod
    def get_business_overview(company, period='monthly'):
        """
        Get comprehensive business analytics overview.
        """
        try:
            end_date = timezone.now().date()
            if period == 'monthly':
                start_date = end_date - timedelta(days=30)
                date_trunc = TruncMonth('issue_date')
            else:  # yearly
                start_date = end_date - timedelta(days=365)
                date_trunc = TruncYear('issue_date')
            
            # Revenue trends
            revenue_trend = Invoice.objects.filter(
                company=company,
                status='PAID',
                issue_date__range=[start_date, end_date]
            ).annotate(
                period=date_trunc
            ).values('period').annotate(
                revenue=Sum('total_amount'),
                growth=Window(
                    expression=F('revenue') - Lag('revenue'),
                    order_by=F('period').asc()
                )
            ).order_by('period')
            
            # Expense trends
            expense_trend = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            ).annotate(
                period=date_trunc
            ).values('period').annotate(
                total=Sum('amount')
            ).order_by('period')
            
            # Client metrics
            client_metrics = Client.objects.filter(
                company=company
            ).aggregate(
                total_clients=Count('id'),
                avg_revenue_per_client=Sum('invoices__total_amount') / Count('id')
            )
            
            return {
                'revenue_analysis': list(revenue_trend),
                'expense_analysis': list(expense_trend),
                'client_metrics': client_metrics,
                'period': period
            }
        except Exception as e:
            logger.error(f"Error generating business overview for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def forecast_cash_flow(company, months=3):
        """
        Generate cash flow forecast using historical data.
        """
        try:
            # Get historical data
            historical_data = Invoice.objects.filter(
                company=company,
                status='PAID'
            ).annotate(
                month=TruncMonth('issue_date')
            ).values('month').annotate(
                revenue=Sum('total_amount')
            ).order_by('month')
            
            # Convert to pandas DataFrame for analysis
            df = pd.DataFrame(historical_data)
            
            if len(df) < 6:  # Need minimum data for forecast
                return None
            
            # Simple moving average forecast
            rolling_avg = df['revenue'].rolling(window=3).mean()
            last_average = rolling_avg.iloc[-1]
            
            # Calculate trend
            trend = (df['revenue'].iloc[-1] - df['revenue'].iloc[0]) / len(df)
            
            # Generate forecast
            forecast = []
            last_date = df['month'].max()
            
            for i in range(months):
                next_month = last_date + timedelta(days=32)
                next_month = next_month.replace(day=1)
                forecast_value = last_average + (trend * (i + 1))
                
                forecast.append({
                    'month': next_month,
                    'forecasted_revenue': max(forecast_value, 0)  # Ensure non-negative
                })
                
                last_date = next_month
            
            return {
                'historical_data': historical_data,
                'forecast': forecast,
                'confidence_level': 'medium'  # Could be calculated based on variance
            }
        except Exception as e:
            logger.error(f"Error generating cash flow forecast for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def get_client_segmentation(company):
        """
        Segment clients based on revenue and payment behavior.
        """
        try:
            clients = Client.objects.filter(company=company).annotate(
                total_revenue=Sum('invoices__total_amount'),
                payment_reliability=Avg(Case(
                    When(invoices__status='PAID', then=1),
                    default=0,
                    output_field=FloatField()
                )),
                avg_days_to_pay=Avg(
                    F('invoices__payments__payment_date') - F('invoices__issue_date')
                )
            )
            
            segments = {
                'high_value': [],
                'medium_value': [],
                'low_value': [],
                'at_risk': []
            }
            
            for client in clients:
                if not client.total_revenue:
                    continue
                
                # Determine segment based on revenue and payment behavior
                if client.total_revenue > 10000 and client.payment_reliability > 0.8:
                    segment = 'high_value'
                elif client.total_revenue > 5000 and client.payment_reliability > 0.6:
                    segment = 'medium_value'
                elif client.payment_reliability < 0.4:
                    segment = 'at_risk'
                else:
                    segment = 'low_value'
                
                segments[segment].append({
                    'client': client,
                    'total_revenue': client.total_revenue,
                    'payment_reliability': client.payment_reliability,
                    'avg_days_to_pay': client.avg_days_to_pay
                })
            
            return segments
        except Exception as e:
            logger.error(f"Error performing client segmentation for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def get_performance_metrics(company, period='yearly'):
        """
        Calculate key performance indicators (KPIs).
        """
        try:
            end_date = timezone.now().date()
            if period == 'monthly':
                start_date = end_date - timedelta(days=30)
            else:  # yearly
                start_date = end_date - timedelta(days=365)
            
            # Financial metrics
            invoices = Invoice.objects.filter(
                company=company,
                issue_date__range=[start_date, end_date]
            )
            
            expenses = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            )
            
            total_revenue = invoices.filter(
                status='PAID'
            ).aggregate(
                total=Sum('total_amount')
            )['total'] or Decimal('0')
            
            total_expenses = expenses.aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            # Calculate metrics
            metrics = {
                'financial': {
                    'total_revenue': total_revenue,
                    'total_expenses': total_expenses,
                    'net_profit': total_revenue - total_expenses,
                    'profit_margin': (
                        (total_revenue - total_expenses) / total_revenue * 100
                        if total_revenue > 0 else 0
                    ),
                    'expense_ratio': (
                        total_expenses / total_revenue * 100
                        if total_revenue > 0 else 0
                    )
                },
                'operational': {
                    'total_invoices': invoices.count(),
                    'paid_invoices': invoices.filter(status='PAID').count(),
                    'overdue_invoices': invoices.filter(status='OVERDUE').count(),
                    'average_invoice_value': (
                        total_revenue / invoices.filter(status='PAID').count()
                        if invoices.filter(status='PAID').exists() else 0
                    )
                },
                'collection': {
                    'days_sales_outstanding': PaymentRecord.objects.filter(
                        invoice__company=company,
                        status='COMPLETED',
                        payment_date__range=[start_date, end_date]
                    ).annotate(
                        collection_days=F('payment_date') - F('invoice__issue_date')
                    ).aggregate(
                        avg_days=Avg('collection_days')
                    )['avg_days'] or 0,
                    'collection_ratio': (
                        invoices.filter(status='PAID').count() /
                        invoices.count() * 100
                        if invoices.exists() else 0
                    )
                },
                'growth': {
                    'revenue_growth': self.calculate_growth_rate(
                        company, 'revenue', start_date, end_date
                    ),
                    'client_growth': self.calculate_growth_rate(
                        company, 'clients', start_date, end_date
                    ),
                    'profit_growth': self.calculate_growth_rate(
                        company, 'profit', start_date, end_date
                    )
                }
            }
            
            return metrics
        except Exception as e:
            logger.error(f"Error calculating performance metrics for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def calculate_growth_rate(company, metric_type, start_date, end_date):
        """
        Calculate growth rate for various metrics.
        """
        try:
            if metric_type == 'revenue':
                current_value = Invoice.objects.filter(
                    company=company,
                    status='PAID',
                    issue_date__range=[start_date, end_date]
                ).aggregate(
                    total=Sum('total_amount')
                )['total'] or Decimal('0')
                
                previous_period_start = start_date - (end_date - start_date)
                previous_value = Invoice.objects.filter(
                    company=company,
                    status='PAID',
                    issue_date__range=[previous_period_start, start_date]
                ).aggregate(
                    total=Sum('total_amount')
                )['total'] or Decimal('0')
                
            elif metric_type == 'clients':
                current_value = Client.objects.filter(
                    company=company,
                    created_at__lte=end_date
                ).count()
                
                previous_value = Client.objects.filter(
                    company=company,
                    created_at__lte=start_date
                ).count()
                
            elif metric_type == 'profit':
                current_revenue = Invoice.objects.filter(
                    company=company,
                    status='PAID',
                    issue_date__range=[start_date, end_date]
                ).aggregate(
                    total=Sum('total_amount')
                )['total'] or Decimal('0')
                
                current_expenses = Expense.objects.filter(
                    company=company,
                    date__range=[start_date, end_date]
                ).aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0')
                
                current_value = current_revenue - current_expenses
                
                previous_period_start = start_date - (end_date - start_date)
                previous_revenue = Invoice.objects.filter(
                    company=company,
                    status='PAID',
                    issue_date__range=[previous_period_start, start_date]
                ).aggregate(
                    total=Sum('total_amount')
                )['total'] or Decimal('0')
                
                previous_expenses = Expense.objects.filter(
                    company=company,
                    date__range=[previous_period_start, start_date]
                ).aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0')
                
                previous_value = previous_revenue - previous_expenses
            
            if previous_value == 0:
                return 100 if current_value > 0 else 0
            
            growth_rate = ((current_value - previous_value) / previous_value) * 100
            return round(growth_rate, 2)
            
        except Exception as e:
            logger.error(f"Error calculating growth rate for {metric_type}: {str(e)}")
            raise

    @staticmethod
    def get_expense_analysis(company, period='monthly'):
        """
        Analyze expense patterns and trends.
        """
        try:
            end_date = timezone.now().date()
            if period == 'monthly':
                start_date = end_date - timedelta(days=30)
                date_trunc = TruncMonth('date')
            else:  # yearly
                start_date = end_date - timedelta(days=365)
                date_trunc = TruncYear('date')

            # Category breakdown
            category_breakdown = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            ).values('category__name').annotate(
                total=Sum('amount'),
                count=Count('id'),
                average=Avg('amount')
            ).order_by('-total')

            # Time series analysis
            time_series = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            ).annotate(
                period=date_trunc
            ).values('period').annotate(
                total=Sum('amount'),
                count=Count('id')
            ).order_by('period')

            # Recurring vs one-time expenses
            expense_types = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            ).aggregate(
                recurring_total=Sum('amount', filter=Q(is_recurring=True)),
                onetime_total=Sum('amount', filter=Q(is_recurring=False))
            )

            return {
                'category_breakdown': list(category_breakdown),
                'time_series': list(time_series),
                'expense_types': expense_types,
                'metrics': {
                    'total_expenses': sum(item['total'] for item in category_breakdown),
                    'avg_expense_amount': Expense.objects.filter(
                        company=company,
                        date__range=[start_date, end_date]
                    ).aggregate(avg=Avg('amount'))['avg'] or 0,
                    'top_category': category_breakdown[0] if category_breakdown else None
                }
            }
        except Exception as e:
            logger.error(f"Error analyzing expenses for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def get_profitability_analysis(company, period='monthly'):
        """
        Analyze profitability metrics.
        """
        try:
            end_date = timezone.now().date()
            if period == 'monthly':
                start_date = end_date - timedelta(days=30)
                date_trunc = TruncMonth('issue_date')
            else:  # yearly
                start_date = end_date - timedelta(days=365)
                date_trunc = TruncYear('issue_date')

            # Time series of profit margins
            profitability = Invoice.objects.filter(
                company=company,
                status='PAID',
                issue_date__range=[start_date, end_date]
            ).annotate(
                period=date_trunc
            ).values('period').annotate(
                revenue=Sum('total_amount'),
                expenses=Sum('company__expenses__amount', 
                           filter=Q(company__expenses__date__range=[start_date, end_date]))
            ).annotate(
                profit=F('revenue') - F('expenses'),
                margin=Case(
                    When(revenue=0, then=0),
                    default=F('profit') * 100 / F('revenue'),
                    output_field=DecimalField()
                )
            ).order_by('period')

            return {
                'time_series': list(profitability),
                'summary': {
                    'average_margin': profitability.aggregate(
                        avg=Avg('margin')
                    )['avg'] or 0,
                    'best_period': max(profitability, key=lambda x: x['margin'])
                        if profitability else None,
                    'worst_period': min(profitability, key=lambda x: x['margin'])
                        if profitability else None
                }
            }
        except Exception as e:
            logger.error(f"Error analyzing profitability for company {company.id}: {str(e)}")
            raise