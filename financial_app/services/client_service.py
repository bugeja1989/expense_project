from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Avg, F, Q
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging
from ..models import Client, Invoice, PaymentRecord

logger = logging.getLogger(__name__)

class ClientService:
    @staticmethod
    def get_client_dashboard(client):
        """
        Get comprehensive client dashboard data.
        """
        try:
            today = timezone.now().date()
            
            # Basic statistics
            stats = {
                'total_invoices': Invoice.objects.filter(client=client).count(),
                'outstanding_balance': Invoice.objects.filter(
                    client=client,
                    status__in=['SENT', 'OVERDUE']
                ).aggregate(
                    total=Sum(F('total_amount') - F('amount_paid'))
                )['total'] or Decimal('0'),
                'paid_invoices': Invoice.objects.filter(
                    client=client,
                    status='PAID'
                ).count(),
                'average_payment_days': PaymentRecord.objects.filter(
                    invoice__client=client,
                    status='COMPLETED'
                ).annotate(
                    days_to_pay=F('payment_date') - F('invoice__issue_date')
                ).aggregate(
                    avg_days=Avg('days_to_pay')
                )['avg_days'] or 0
            }
            
            # Payment history
            payment_history = PaymentRecord.objects.filter(
                invoice__client=client
            ).order_by('-payment_date')[:10]
            
            # Recent invoices
            recent_invoices = Invoice.objects.filter(
                client=client
            ).order_by('-issue_date')[:5]
            
            return {
                'statistics': stats,
                'payment_history': payment_history,
                'recent_invoices': recent_invoices,
                'credit_status': {
                    'limit': client.credit_limit,
                    'available': client.credit_limit - stats['outstanding_balance'] if client.credit_limit else None,
                    'is_exceeded': client.is_credit_limit_exceeded()
                }
            }
        except Exception as e:
            logger.error(f"Error generating client dashboard for client {client.id}: {str(e)}")
            raise

    @staticmethod
    def analyze_payment_behavior(client):
        """
        Analyze client payment behavior and patterns.
        """
        try:
            paid_invoices = Invoice.objects.filter(
                client=client,
                status='PAID'
            ).annotate(
                days_to_pay=F('payments__payment_date') - F('issue_date')
            )
            
            analysis = {
                'average_payment_time': paid_invoices.aggregate(
                    avg_days=Avg('days_to_pay')
                )['avg_days'] or 0,
                'on_time_payments': paid_invoices.filter(
                    payments__payment_date__lte=F('due_date')
                ).count(),
                'late_payments': paid_invoices.filter(
                    payments__payment_date__gt=F('due_date')
                ).count(),
                'payment_methods': PaymentRecord.objects.filter(
                    invoice__client=client
                ).values('payment_method').annotate(
                    count=Count('id')
                )
            }
            
            return analysis
        except Exception as e:
            logger.error(f"Error analyzing payment behavior for client {client.id}: {str(e)}")
            raise

    @staticmethod
    def send_statement(client, start_date, end_date):
        """
        Generate and send client statement via email.
        """
        try:
            from .report_service import ReportService
            statement = ReportService.generate_client_statement(client, start_date, end_date)
            
            context = {
                'client': client,
                'statement': statement,
                'company': client.company
            }
            
            html_message = render_to_string(
                'financial_app/email/client_statement.html',
                context
            )
            
            send_mail(
                subject=f'Account Statement - {start_date.strftime("%B %Y")} to {end_date.strftime("%B %Y")}',
                message='',
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[client.email],
                fail_silently=False
            )
        except Exception as e:
            logger.error(f"Error sending statement to client {client.id}: {str(e)}")
            raise

    @staticmethod
    def check_credit_status(client):
        """
        Check client's credit status and send alerts if needed.
        """
        try:
            if not client.credit_limit:
                return None
                
            outstanding_balance = client.get_outstanding_balance()
            credit_used_percentage = (outstanding_balance / client.credit_limit) * 100
            
            status = {
                'total_outstanding': outstanding_balance,
                'credit_limit': client.credit_limit,
                'credit_available': client.credit_limit - outstanding_balance,
                'credit_used_percentage': credit_used_percentage,
                'is_exceeded': outstanding_balance > client.credit_limit,
                'alert_level': 'normal'
            }
            
            # Determine alert level
            if credit_used_percentage >= 90:
                status['alert_level'] = 'critical'
            elif credit_used_percentage >= 75:
                status['alert_level'] = 'warning'
            
            # Send alert if needed
            if status['alert_level'] in ['warning', 'critical']:
                context = {
                    'client': client,
                    'status': status
                }
                
                html_message = render_to_string(
                    'financial_app/email/credit_limit_alert.html',
                    context
                )
                
                send_mail(
                    subject=f'Credit Limit Alert - {client.name}',
                    message='',
                    html_message=html_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[client.company.owner.email],
                    fail_silently=True
                )
            
            return status
        except Exception as e:
            logger.error(f"Error checking credit status for client {client.id}: {str(e)}")
            raise

    @staticmethod
    def get_revenue_analysis(client, period='yearly'):
        """
        Analyze client revenue over time.
        """
        try:
            paid_invoices = Invoice.objects.filter(
                client=client,
                status='PAID'
            )
            
            if period == 'monthly':
                analysis = paid_invoices.annotate(
                    period=F('issue_date__month')
                ).values('period').annotate(
                    revenue=Sum('total_amount'),
                    invoice_count=Count('id')
                ).order_by('period')
            else:  # yearly
                analysis = paid_invoices.annotate(
                    period=F('issue_date__year')
                ).values('period').annotate(
                    revenue=Sum('total_amount'),
                    invoice_count=Count('id')
                ).order_by('period')
            
            return {
                'revenue_by_period': list(analysis),
                'total_revenue': paid_invoices.aggregate(
                    total=Sum('total_amount')
                )['total'] or Decimal('0'),
                'average_invoice_value': paid_invoices.aggregate(
                    avg=Avg('total_amount')
                )['avg'] or Decimal('0')
            }
        except Exception as e:
            logger.error(f"Error analyzing revenue for client {client.id}: {str(e)}")
            raise

    @staticmethod
    def get_communication_history(client):
        """
        Get history of all communications with client.
        """
        try:
            from django.contrib.admin.models import LogEntry
            from actstream.models import Action
            
            # Get system logs
            logs = LogEntry.objects.filter(
                content_type__model='client',
                object_id=str(client.id)
            ).order_by('-action_time')
            
            # Get activity stream
            activities = Action.objects.filter(
                target_object_id=client.id
            ).order_by('-timestamp')
            
            return {
                'system_logs': logs,
                'activities': activities
            }
        except Exception as e:
            logger.error(f"Error getting communication history for client {client.id}: {str(e)}")
            raise