from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from django.db.models import Sum
import pdfkit
import logging
from ..models import Invoice, PaymentRecord

logger = logging.getLogger(__name__)

class InvoiceService:
    @staticmethod
    def create_invoice(company, client, items, **kwargs):
        """
        Create a new invoice with items.
        """
        try:
            invoice = Invoice.objects.create(
                company=company,
                client=client,
                issue_date=kwargs.get('issue_date', timezone.now().date()),
                due_date=kwargs.get('due_date'),
                tax_rate=kwargs.get('tax_rate', Decimal('0')),
                notes=kwargs.get('notes', ''),
                terms=kwargs.get('terms', ''),
                created_by=kwargs.get('created_by'),
                is_recurring=kwargs.get('is_recurring', False),
                recurring_frequency=kwargs.get('recurring_frequency', '')
            )

            # Create invoice items
            for item in items:
                invoice.items.create(
                    description=item['description'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    tax_rate=item.get('tax_rate', Decimal('0'))
                )

            return invoice
        except Exception as e:
            logger.error(f"Error creating invoice: {str(e)}")
            raise

    @staticmethod
    def generate_pdf(invoice):
        """
        Generate PDF version of the invoice.
        """
        try:
            context = {
                'invoice': invoice,
                'company': invoice.company,
                'client': invoice.client,
                'items': invoice.items.all()
            }

            html_content = render_to_string(
                'financial_app/pdf/invoice_template.html',
                context
            )

            pdf_file = pdfkit.from_string(html_content, False)
            return pdf_file
        except Exception as e:
            logger.error(f"Error generating PDF for invoice {invoice.id}: {str(e)}")
            raise

    @staticmethod
    def send_invoice(invoice, pdf_file=None):
        """
        Send invoice to client via email.
        """
        try:
            context = {
                'invoice': invoice,
                'company': invoice.company,
                'client': invoice.client
            }

            html_message = render_to_string(
                'financial_app/email/invoice_email.html',
                context
            )

            email = EmailMessage(
                subject=f'Invoice {invoice.invoice_number} from {invoice.company.name}',
                body=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[invoice.client.email]
            )

            if pdf_file:
                email.attach(
                    f'invoice_{invoice.invoice_number}.pdf',
                    pdf_file,
                    'application/pdf'
                )

            email.send()

            invoice.status = 'SENT'
            invoice.save()
        except Exception as e:
            logger.error(f"Error sending invoice {invoice.id}: {str(e)}")
            raise

    @staticmethod
    def record_payment(invoice, amount, payment_method, **kwargs):
        """
        Record a payment for an invoice.
        """
        try:
            payment = PaymentRecord.objects.create(
                invoice=invoice,
                amount=amount,
                payment_date=kwargs.get('payment_date', timezone.now().date()),
                payment_method=payment_method,
                transaction_id=kwargs.get('transaction_id', ''),
                reference_number=kwargs.get('reference_number', ''),
                notes=kwargs.get('notes', ''),
                processed_by=kwargs.get('processed_by'),
                status='COMPLETED'
            )

            # Update invoice amount paid and status
            invoice.amount_paid = invoice.payments.filter(
                status='COMPLETED'
            ).aggregate(
                total=Sum('amount')
            )['total'] or 0

            if invoice.amount_paid >= invoice.total_amount:
                invoice.status = 'PAID'
            elif invoice.amount_paid > 0:
                invoice.status = 'PARTIALLY_PAID'
            
            invoice.save()

            return payment
        except Exception as e:
            logger.error(f"Error recording payment for invoice {invoice.id}: {str(e)}")
            raise

    @staticmethod
    def void_invoice(invoice, reason, user):
        """
        Void an invoice and record the reason.
        """
        try:
            if invoice.status == 'PAID':
                raise ValueError("Cannot void a paid invoice")

            invoice.status = 'CANCELLED'
            invoice.notes += f"\nVoided on {timezone.now()} by {user.username}\nReason: {reason}"
            invoice.save()
        except Exception as e:
            logger.error(f"Error voiding invoice {invoice.id}: {str(e)}")
            raise

    @staticmethod
    def get_aging_report(company, as_of_date=None):
        """
        Generate aging report for unpaid invoices.
        """
        try:
            if not as_of_date:
                as_of_date = timezone.now().date()

            aging_periods = {
                'current': (0, 30),
                '31-60': (31, 60),
                '61-90': (61, 90),
                'over_90': (91, float('inf'))
            }

            report = {period: Decimal('0') for period in aging_periods}

            unpaid_invoices = Invoice.objects.filter(
                company=company,
                status__in=['SENT', 'OVERDUE', 'PARTIALLY_PAID']
            )

            for invoice in unpaid_invoices:
                days_outstanding = (as_of_date - invoice.due_date).days
                balance_due = invoice.total_amount - invoice.amount_paid

                for period, (min_days, max_days) in aging_periods.items():
                    if min_days <= days_outstanding <= max_days:
                        report[period] += balance_due
                        break

            return report
        except Exception as e:
            logger.error(f"Error generating aging report for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def calculate_late_fees(invoice):
        """
        Calculate late fees for overdue invoice.
        """
        try:
            if not invoice.is_overdue():
                return Decimal('0')

            days_overdue = (timezone.now().date() - invoice.due_date).days
            late_fee_rate = invoice.company.late_fee_rate or Decimal('0.01')  # 1% per month default
            daily_rate = late_fee_rate / Decimal('30')
            
            late_fee = invoice.total_amount * daily_rate * Decimal(str(days_overdue))
            return late_fee.quantize(Decimal('0.01'))
        except Exception as e:
            logger.error(f"Error calculating late fees for invoice {invoice.id}: {str(e)}")
            raise