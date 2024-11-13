from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from decimal import Decimal, ROUND_HALF_UP
import uuid
import re
import magic
import os
from datetime import datetime, timedelta

class NumberFormatter:
    """
    Utility class for number formatting and calculations.
    """
    @staticmethod
    def format_currency(amount, currency='EUR', decimal_places=2):
        """Format amount as currency string."""
        try:
            decimal_amount = Decimal(str(amount))
            formatted = decimal_amount.quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP
            )
            if currency == 'EUR':
                return f'€{formatted:,.2f}'
            elif currency == 'USD':
                return f'${formatted:,.2f}'
            elif currency == 'GBP':
                return f'£{formatted:,.2f}'
            return f'{formatted:,.2f} {currency}'
        except:
            return '0.00'

    @staticmethod
    def calculate_percentage(part, whole):
        """Calculate percentage with proper rounding."""
        try:
            if whole == 0:
                return Decimal('0.00')
            result = (Decimal(str(part)) / Decimal(str(whole))) * 100
            return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except:
            return Decimal('0.00')

    @staticmethod
    def round_decimal(value, places=2):
        """Round decimal to specified places."""
        try:
            return Decimal(str(value)).quantize(
                Decimal('0.{}'.format('0' * places)),
                rounding=ROUND_HALF_UP
            )
        except:
            return Decimal('0.00')

class DateTimeUtil:
    """
    Utility class for date and time operations.
    """
    @staticmethod
    def get_date_range(period='month'):
        """Get start and end dates for given period."""
        today = timezone.now().date()
        
        if period == 'today':
            return today, today
        elif period == 'week':
            start = today - timedelta(days=today.weekday())
            return start, today
        elif period == 'month':
            start = today.replace(day=1)
            return start, today
        elif period == 'quarter':
            quarter = (today.month - 1) // 3
            start = today.replace(month=quarter * 3 + 1, day=1)
            return start, today
        elif period == 'year':
            start = today.replace(month=1, day=1)
            return start, today
        return None, None

    @staticmethod
    def format_date(date, format='%Y-%m-%d'):
        """Format date to string."""
        try:
            return date.strftime(format)
        except:
            return ''

    @staticmethod
    def parse_date(date_string, format='%Y-%m-%d'):
        """Parse date from string."""
        try:
            return datetime.strptime(date_string, format).date()
        except:
            return None

class FileHandler:
    """
    Utility class for file operations.
    """
    ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif']
    ALLOWED_DOCUMENT_TYPES = ['application/pdf', 'application/msword',
                             'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    @staticmethod
    def validate_file_type(file, allowed_types=None):
        """Validate file type using magic numbers."""
        if not allowed_types:
            allowed_types = FileHandler.ALLOWED_IMAGE_TYPES + FileHandler.ALLOWED_DOCUMENT_TYPES
            
        try:
            file_type = magic.from_buffer(file.read(1024), mime=True)
            file.seek(0)  # Reset file pointer
            
            if file_type not in allowed_types:
                raise ValidationError(_('Invalid file type'))
                
            return file_type
        except Exception as e:
            raise ValidationError(_('Error validating file type'))

    @staticmethod
    def validate_file_size(file, max_size=None):
        """Validate file size."""
        if not max_size:
            max_size = FileHandler.MAX_FILE_SIZE
            
        if file.size > max_size:
            raise ValidationError(
                _('File size cannot exceed %(size)s MB') % {
                    'size': max_size / (1024 * 1024)
                }
            )

    @staticmethod
    def generate_unique_filename(filename):
        """Generate unique filename with UUID."""
        name, ext = os.path.splitext(filename)
        return f"{uuid.uuid4().hex}{ext}"

class EmailHandler:
    """
    Utility class for email operations.
    """
    @staticmethod
    def send_template_email(template_name, context, subject, recipient_list,
                          from_email=None, attachments=None):
        """Send email using template."""
        if not from_email:
            from_email = settings.DEFAULT_FROM_EMAIL

        html_message = render_to_string(f'financial_app/email/{template_name}.html', context)
        
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=from_email,
            to=recipient_list
        )
        email.content_subtype = 'html'
        
        if attachments:
            for attachment in attachments:
                email.attach_file(attachment)
                
        return email.send()

    @staticmethod
    def validate_email(email):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            raise ValidationError(_('Invalid email format'))
        return email

class Validator:
    """
    Utility class for various validations.
    """
    @staticmethod
    def validate_phone(phone):
        """Validate phone number format."""
        pattern = r'^\+?1?\d{9,15}$'
        if not re.match(pattern, phone):
            raise ValidationError(_('Invalid phone number format'))
        return phone

    @staticmethod
    def validate_vat_number(vat_number):
        """Validate VAT number format."""
        # Basic VAT format validation - customize based on your needs
        pattern = r'^[A-Z]{2}\d{8,12}$'
        if not re.match(pattern, vat_number.upper()):
            raise ValidationError(_('Invalid VAT number format'))
        return vat_number.upper()

    @staticmethod
    def validate_decimal(value, min_value=None, max_value=None):
        """Validate decimal value."""
        try:
            decimal_value = Decimal(str(value))
            if min_value is not None and decimal_value < Decimal(str(min_value)):
                raise ValidationError(
                    _('Value must be greater than or equal to %(min)s') % {
                        'min': min_value
                    }
                )
            if max_value is not None and decimal_value > Decimal(str(max_value)):
                raise ValidationError(
                    _('Value must be less than or equal to %(max)s') % {
                        'max': max_value
                    }
                )
            return decimal_value
        except (TypeError, ValueError):
            raise ValidationError(_('Invalid decimal value'))

class SecurityUtil:
    """
    Utility class for security operations.
    """
    @staticmethod
    def mask_sensitive_data(data, fields=None):
        """Mask sensitive data for logging."""
        if not fields:
            fields = ['password', 'credit_card', 'secret']
            
        if isinstance(data, dict):
            masked_data = data.copy()
            for field in fields:
                if field in masked_data:
                    masked_data[field] = '*' * 8
            return masked_data
        return data

    @staticmethod
    def generate_random_string(length=32):
        """Generate random string for security purposes."""
        return uuid.uuid4().hex[:length]

    @staticmethod
    def is_safe_url(url):
        """Check if URL is safe for redirects."""
        from django.utils.http import url_has_allowed_host_and_scheme
        return url_has_allowed_host_and_scheme(
            url=url,
            allowed_hosts=settings.ALLOWED_HOSTS,
            require_https=settings.SECURE_SSL_REDIRECT
        )

# Global utility functions
def format_file_size(size):
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def truncate_string(value, length=50, suffix='...'):
    """Truncate string to specified length."""
    if not value:
        return ''
    if len(value) <= length:
        return value
    return value[:length].rsplit(' ', 1)[0] + suffix