from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import EmailValidator, ValidationError
from ..models import Client
import re

class ClientForm(forms.ModelForm):
    """
    Form for creating and editing clients.
    """
    confirm_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': _('Confirm email address')
        })
    )

    class Meta:
        model = Client
        fields = [
            'name', 'email', 'phone', 'address', 'vat_number',
            'contact_person', 'notes', 'payment_terms', 'credit_limit',
            'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Client name or company')
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': _('Email address')
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Phone number')
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Full address')
            }),
            'vat_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('VAT/Tax number')
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Primary contact person')
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Additional notes about the client')
            }),
            'payment_terms': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': _('Payment terms in days')
            }),
            'credit_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': _('Credit limit amount')
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if self.instance.pk:  # If editing existing client
            self.fields['confirm_email'].initial = self.instance.email
            
        # Set initial payment terms from company settings if available
        if self.company and not self.instance.pk:
            self.fields['payment_terms'].initial = self.company.default_payment_terms

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        # Remove all non-digit characters except + (for international numbers)
        phone = re.sub(r'[^\d+]', '', phone)
        
        # Validate phone number format
        if not re.match(r'^\+?[\d\s-]{8,}$', phone):
            raise ValidationError(_("Enter a valid phone number"))
        
        return phone

    def clean_vat_number(self):
        vat_number = self.cleaned_data['vat_number']
        if vat_number:
            # Remove whitespace and convert to uppercase
            vat_number = vat_number.upper().replace(' ', '')
            
            # Basic VAT number validation (can be customized based on country)
            if not re.match(r'^[A-Z0-9]{8,}$', vat_number):
                raise ValidationError(_("Enter a valid VAT number"))
        
        return vat_number

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        confirm_email = cleaned_data.get('confirm_email')
        payment_terms = cleaned_data.get('payment_terms')
        credit_limit = cleaned_data.get('credit_limit')

        if email and confirm_email and email != confirm_email:
            raise ValidationError({
                'confirm_email': _("Email addresses must match")
            })

        # Validate unique email within company
        if email and self.company:
            exists = Client.objects.filter(
                company=self.company,
                email__iexact=email
            ).exclude(pk=self.instance.pk).exists()
            
            if exists:
                raise ValidationError({
                    'email': _("A client with this email already exists")
                })

        if payment_terms is not None and payment_terms < 0:
            raise ValidationError({
                'payment_terms': _("Payment terms cannot be negative")
            })

        if credit_limit is not None and credit_limit < 0:
            raise ValidationError({
                'credit_limit': _("Credit limit cannot be negative")
            })

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.company = self.company
        
        if commit:
            instance.save()
        
        return instance

class ClientBulkUploadForm(forms.Form):
    """
    Form for bulk uploading clients via CSV/Excel file.
    """
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx,.xls'
        })
    )
    
    update_existing = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Update existing clients if email matches")
    )

    def clean_file(self):
        file = self.cleaned_data['file']
        ext = str(file.name).lower().split('.')[-1]
        
        if ext not in ['csv', 'xlsx', 'xls']:
            raise ValidationError(_("Please upload a CSV or Excel file"))
            
        if file.size > 5 * 1024 * 1024:  # 5MB limit
            raise ValidationError(_("File size cannot exceed 5MB"))
            
        return file

class ClientNoteForm(forms.Form):
    """
    Form for adding notes to client records.
    """
    note = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Add a note about this client')
        })
    )
    
    private = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Make this note private (visible only to staff)")
    )

class ClientFilterForm(forms.Form):
    """
    Form for filtering client list.
    """
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Search by name, email, or VAT number')
        })
    )
    
    is_active = forms.ChoiceField(
        required=False,
        choices=[
            ('', _('All Clients')),
            ('1', _('Active Clients')),
            ('0', _('Inactive Clients'))
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    
    has_overdue = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        label=_("Has overdue invoices")
    )
    
    min_balance = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'placeholder': _('Minimum balance')
        })
    )
    
    max_balance = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'placeholder': _('Maximum balance')
        })
    )
    
    sort_by = forms.ChoiceField(
        required=False,
        choices=[
            ('name', _('Name')),
            ('email', _('Email')),
            ('balance', _('Outstanding Balance')),
            ('created_at', _('Date Added')),
            ('last_invoice', _('Last Invoice Date'))
        ],
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        min_balance = cleaned_data.get('min_balance')
        max_balance = cleaned_data.get('max_balance')
        
        if min_balance and max_balance and min_balance > max_balance:
            raise ValidationError(_("Maximum balance must be greater than minimum balance"))
            
        return cleaned_data