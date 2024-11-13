from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Case, When, F, Q, Value
from django.db.models.functions import TruncMonth, TruncYear, ExtractYear, Coalesce
from django.core.files.storage import default_storage
import csv
import io
import logging
from datetime import datetime, timedelta
import xlsxwriter
from ..models import Invoice, Expense, Client, PaymentRecord

logger = logging.getLogger(__name__)

class ReportService:
    @staticmethod
    def generate_pl_statement(company, start_date, end_date):
        """
        Generate Profit & Loss statement.
        """
        try:
            # Calculate revenue
            revenue_data = Invoice.objects.filter(
                company=company,
                status='PAID',
                issue_date__range=[start_date, end_date]
            ).aggregate(
                total_revenue=Coalesce(Sum('total_amount'), Decimal('0')),
                total_tax=Coalesce(Sum('tax_amount'), Decimal('0'))
            )

            # Calculate expenses with categories
            expenses = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            )
            
            expense_summary = expenses.values('category__name').annotate(
                total=Coalesce(Sum('amount'), Decimal('0'))
            ).order_by('-total')

            total_expenses = expenses.aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'))
            )['total']

            # Calculate gross profit and net profit
            gross_profit = revenue_data['total_revenue'] - total_expenses
            net_profit = gross_profit - revenue_data['total_tax']

            return {
                'period_start': start_date,
                'period_end': end_date,
                'revenue': {
                    'total': revenue_data['total_revenue'],
                    'tax': revenue_data['total_tax']
                },
                'expenses': {
                    'breakdown': expense_summary,
                    'total': total_expenses
                },
                'profits': {
                    'gross': gross_profit,
                    'net': net_profit
                },
                'metrics': {
                    'gross_margin': (gross_profit / revenue_data['total_revenue'] * 100) if revenue_data['total_revenue'] else 0,
                    'net_margin': (net_profit / revenue_data['total_revenue'] * 100) if revenue_data['total_revenue'] else 0
                }
            }
        except Exception as e:
            logger.error(f"Error generating P&L statement for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def generate_cash_flow_statement(company, start_date, end_date):
        """
        Generate Cash Flow statement.
        """
        try:
            # Operating Activities
            # Cash inflows from payments received
            cash_inflows = PaymentRecord.objects.filter(
                invoice__company=company,
                status='COMPLETED',
                payment_date__range=[start_date, end_date]
            ).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'))
            )['total']

            # Cash outflows from expenses
            cash_outflows = Expense.objects.filter(
                company=company,
                date__range=[start_date, end_date]
            ).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'))
            )['total']

            # Calculate monthly breakdown
            monthly_cash_flow = PaymentRecord.objects.filter(
                invoice__company=company,
                payment_date__range=[start_date, end_date]
            ).annotate(
                month=TruncMonth('payment_date')
            ).values('month').annotate(
                inflow=Coalesce(Sum(Case(
                    When(status='COMPLETED', then='amount'),
                    default=Value(0)
                )), Decimal('0')),
                outflow=Coalesce(Sum(Case(
                    When(status='REFUNDED', then='amount'),
                    default=Value(0)
                )), Decimal('0'))
            ).order_by('month')

            return {
                'period_start': start_date,
                'period_end': end_date,
                'operating_activities': {
                    'inflows': cash_inflows,
                    'outflows': cash_outflows,
                    'net': cash_inflows - cash_outflows
                },
                'monthly_breakdown': monthly_cash_flow,
                'metrics': {
                    'cash_conversion_ratio': (cash_inflows / cash_outflows * 100) if cash_outflows else 0
                }
            }
        except Exception as e:
            logger.error(f"Error generating cash flow statement for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def generate_accounts_receivable_report(company, as_of_date=None):
        """
        Generate Accounts Receivable aging report.
        """
        try:
            if not as_of_date:
                as_of_date = timezone.now().date()

            aging_periods = {
                'current': (0, 30),
                '31-60': (31, 60),
                '61-90': (61, 90),
                'over_90': (91, None)
            }

            unpaid_invoices = Invoice.objects.filter(
                company=company,
                status__in=['SENT', 'OVERDUE', 'PARTIALLY_PAID']
            )

            aging_report = {
                'details': [],
                'summary': {period: Decimal('0') for period in aging_periods}
            }

            for invoice in unpaid_invoices:
                days_outstanding = (as_of_date - invoice.issue_date).days
                balance_due = invoice.total_amount - invoice.amount_paid

                # Determine aging period
                for period, (min_days, max_days) in aging_periods.items():
                    if max_days is None:
                        if days_outstanding >= min_days:
                            aging_period = period
                            break
                    elif min_days <= days_outstanding <= max_days:
                        aging_period = period
                        break

                aging_report['summary'][aging_period] += balance_due
                aging_report['details'].append({
                    'invoice_number': invoice.invoice_number,
                    'client': invoice.client.name,
                    'issue_date': invoice.issue_date,
                    'due_date': invoice.due_date,
                    'total_amount': invoice.total_amount,
                    'balance_due': balance_due,
                    'days_outstanding': days_outstanding,
                    'aging_period': aging_period
                })

            return aging_report
        except Exception as e:
            logger.error(f"Error generating AR aging report for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def generate_tax_report(company, tax_year):
        """
        Generate tax report for a specific year.
        """
        try:
            start_date = datetime(tax_year, 1, 1).date()
            end_date = datetime(tax_year, 12, 31).date()

            # Tax collected from invoices
            tax_collected = Invoice.objects.filter(
                company=company,
                status='PAID',
                issue_date__range=[start_date, end_date]
            ).aggregate(
                total_tax=Coalesce(Sum('tax_amount'), Decimal('0'))
            )['total_tax']

            # Tax deductible expenses
            tax_deductible_expenses = Expense.objects.filter(
                company=company,
                tax_deductible=True,
                date__range=[start_date, end_date]
            ).values('category__name').annotate(
                total=Coalesce(Sum('amount'), Decimal('0'))
            ).order_by('-total')

            total_deductible = sum(item['total'] for item in tax_deductible_expenses)

            return {
                'year': tax_year,
                'tax_collected': tax_collected,
                'tax_deductible_expenses': {
                    'breakdown': tax_deductible_expenses,
                    'total': total_deductible
                },
                'net_tax_position': tax_collected - total_deductible
            }
        except Exception as e:
            logger.error(f"Error generating tax report for company {company.id}: {str(e)}")
            raise

    @staticmethod
    def export_report_to_excel(report_data, report_type):
        """
        Export report data to Excel format.
        """
        try:
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet()

            # Add headers
            headers = []
            if report_type == 'pl':
                headers = ['Category', 'Amount']
            elif report_type == 'cash_flow':
                headers = ['Month', 'Inflows', 'Outflows', 'Net']
            elif report_type == 'ar_aging':
                headers = ['Invoice Number', 'Client', 'Issue Date', 'Due Date', 
                         'Total Amount', 'Balance Due', 'Days Outstanding']

            for col, header in enumerate(headers):
                worksheet.write(0, col, header)

            # Add data
            row = 1
            if report_type == 'pl':
                for item in report_data['expenses']['breakdown']:
                    worksheet.write(row, 0, item['category__name'])
                    worksheet.write(row, 1, float(item['total']))
                    row += 1
            elif report_type == 'ar_aging':
                for item in report_data['details']:
                    worksheet.write(row, 0, item['invoice_number'])
                    worksheet.write(row, 1, item['client'])
                    worksheet.write(row, 2, item['issue_date'].strftime('%Y-%m-%d'))
                    worksheet.write(row, 3, item['due_date'].strftime('%Y-%m-%d'))
                    worksheet.write(row, 4, float(item['total_amount']))
                    worksheet.write(row, 5, float(item['balance_due']))
                    worksheet.write(row, 6, item['days_outstanding'])
                    row += 1

            workbook.close()
            output.seek(0)
            return output
        except Exception as e:
            logger.error(f"Error exporting report to Excel: {str(e)}")
            raise

    @staticmethod
    def generate_client_statement(client, start_date, end_date):
        """
        Generate client statement showing all transactions.
        """
        try:
            invoices = Invoice.objects.filter(
                client=client,
                issue_date__range=[start_date, end_date]
            ).order_by('issue_date')

            payments = PaymentRecord.objects.filter(
                invoice__client=client,
                payment_date__range=[start_date, end_date]
            ).order_by('payment_date')

            transactions = []
            balance = Decimal('0')

            # Combine invoices and payments into a single timeline
            for invoice in invoices:
                balance += invoice.total_amount
                transactions.append({
                    'date': invoice.issue_date,
                    'type': 'Invoice',
                    'reference': invoice.invoice_number,
                    'amount': invoice.total_amount,
                    'balance': balance
                })

            for payment in payments:
                balance -= payment.amount
                transactions.append({
                    'date': payment.payment_date,
                    'type': 'Payment',
                    'reference': payment.reference_number,
                    'amount': -payment.amount,
                    'balance': balance
                })

            transactions.sort(key=lambda x: x['date'])

            return {
                'client': client,
                'period_start': start_date,
                'period_end': end_date,
                'transactions': transactions,
                'opening_balance': Decimal('0'),  # You might want to calculate this
                'closing_balance': balance
            }
        except Exception as e:
            logger.error(f"Error generating client statement for client {client.id}: {str(e)}")
            raise