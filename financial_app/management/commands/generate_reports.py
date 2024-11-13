from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
import os
import logging
from datetime import datetime, timedelta

from financial_app.models import Company
from financial_app.services.report_service import ReportService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate and distribute periodic financial reports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--report-type',
            type=str,
            choices=['monthly', 'quarterly', 'annual'],
            default='monthly',
            help='Type of report to generate'
        )
        
        parser.add_argument(
            '--company-id',
            type=int,
            help='Generate report for specific company ID'
        )
        
        parser.add_argument(
            '--email',
            action='store_true',
            help='Send reports via email'
        )
        
        parser.add_argument(
            '--output-dir',
            type=str,
            help='Directory to save generated reports'
        )
        
        parser.add_argument(
            '--format',
            type=str,
            choices=['pdf', 'xlsx', 'csv'],
            default='pdf',
            help='Output format for reports'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            # Get date range based on report type
            start_date, end_date = self.get_date_range(options['report_type'])
            
            # Get companies to process
            companies = self.get_companies(options.get('company_id'))
            
            self.stdout.write(f"Generating {options['report_type']} reports for {len(companies)} companies")
            
            # Process each company
            for company in companies:
                try:
                    self.process_company(
                        company,
                        start_date,
                        end_date,
                        options
                    )
                except Exception as e:
                    logger.error(f"Error processing company {company.id}: {str(e)}")
                    continue
            
            self.stdout.write(self.style.SUCCESS('Successfully generated reports'))
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            raise CommandError(f"Report generation failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for the command."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'report_generation_{timezone.now().strftime("%Y%m%d")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def get_date_range(self, report_type):
        """Calculate date range based on report type."""
        end_date = timezone.now().date()
        
        if report_type == 'monthly':
            start_date = end_date.replace(day=1)
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        elif report_type == 'quarterly':
            quarter = (end_date.month - 1) // 3
            start_date = end_date.replace(month=quarter * 3 + 1, day=1)
            end_date = (start_date + timedelta(days=95)).replace(day=1) - timedelta(days=1)
        else:  # annual
            start_date = end_date.replace(month=1, day=1)
            end_date = end_date.replace(month=12, day=31)
            
        return start_date, end_date

    def get_companies(self, company_id=None):
        """Get companies to process."""
        if company_id:
            return Company.objects.filter(id=company_id)
        return Company.objects.filter(is_active=True)

    def process_company(self, company, start_date, end_date, options):
        """Process reports for a single company."""
        # Generate reports
        reports = {
            'profit_loss': ReportService.generate_pl_statement(
                company, start_date, end_date
            ),
            'cash_flow': ReportService.generate_cash_flow_statement(
                company, start_date, end_date
            ),
            'tax': ReportService.generate_tax_report(
                company, start_date.year
            )
        }
        
        # Save reports if output directory specified
        if options.get('output_dir'):
            self.save_reports(
                company,
                reports,
                options['output_dir'],
                options['format']
            )
        
        # Send email if requested
        if options.get('email'):
            self.send_report_email(
                company,
                reports,
                start_date,
                end_date,
                options['format']
            )

    def save_reports(self, company, reports, output_dir, format_type):
        """Save generated reports to files."""
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        company_dir = os.path.join(output_dir, f"company_{company.id}")
        
        if not os.path.exists(company_dir):
            os.makedirs(company_dir)
        
        for report_type, report_data in reports.items():
            filename = f"{report_type}_{timestamp}.{format_type}"
            filepath = os.path.join(company_dir, filename)
            
            if format_type == 'pdf':
                ReportService.export_as_pdf(report_data, filepath)
            elif format_type == 'xlsx':
                ReportService.export_as_excel(report_data, filepath)
            else:  # csv
                ReportService.export_as_csv(report_data, filepath)
            
            logger.info(f"Saved {report_type} report for company {company.id}: {filepath}")

    def send_report_email(self, company, reports, start_date, end_date, format_type):
        """Send reports via email."""
        try:
            context = {
                'company': company,
                'start_date': start_date,
                'end_date': end_date,
                'reports': reports
            }
            
            html_message = render_to_string(
                'financial_app/email/periodic_reports.html',
                context
            )
            
            email = EmailMessage(
                subject=f'Financial Reports {start_date} - {end_date}',
                body=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[company.owner.email]
            )
            
            # Attach report files
            for report_type, report_data in reports.items():
                attachment = None
                if format_type == 'pdf':
                    attachment = ReportService.export_as_pdf(report_data)
                elif format_type == 'xlsx':
                    attachment = ReportService.export_as_excel(report_data)
                else:  # csv
                    attachment = ReportService.export_as_csv(report_data)
                
                if attachment:
                    email.attach(
                        f"{report_type}.{format_type}",
                        attachment,
                        self.get_mime_type(format_type)
                    )
            
            email.send()
            logger.info(f"Sent reports email to company {company.id}")
            
        except Exception as e:
            logger.error(f"Failed to send email for company {company.id}: {str(e)}")
            raise

    def get_mime_type(self, format_type):
        """Get MIME type for file format."""
        mime_types = {
            'pdf': 'application/pdf',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'csv': 'text/csv'
        }
        return mime_types.get(format_type, 'application/octet-stream')