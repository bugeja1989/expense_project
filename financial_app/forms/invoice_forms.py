from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import Invoice, InvoiceItem, Client
from decimal import Decimal
import json

class InvoiceCreateForm(forms.ModelForm):
    """
    Form for creating a new invoice with multiple items.
    """
    items_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    due_days = forms.IntegerField(
        min_value=0,
        required=False,
        help_text=_("Number of days until invoice is due")
    )
    
    send_to_client = forms.BooleanField(
        required=False,
        initial=False,
        help_text=_("Send invoice to client immediately after creation")
    )

    class Meta:
        model = Invoice
        fields = ['client', 'issue_date', 'due_date', 'tax_rate', 
                 'notes', 'terms', 'is_recurring', 'recurring_frequency']
        widgets = {
            'client': forms.Select(attrs={
                'class': 'form-select',
                'data-placeholder': _('Select a client')
            }),
            'issue_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'tax_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'terms': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'is_recurring': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'recurring_frequency': forms.Select(attrs={
                'class': 'form-select'
            })
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if self.company:
            self.fields['client'].queryset = Client.objects.filter(
                company=self.company,
                is_active=True
            )
            
            # Set default terms from company settings
            if not self.instance.pk:  # Only for new invoices
                self.fields['terms'].initial = self.company.invoice_notes_template
                self.fields['due_days'].initial = self.company.default_payment_terms

    def clean(self):
        cleaned_data = super().clean()
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        due_days = cleaned_data.get('due_days')
        items_json = cleaned_data.get('items_json')

        # Validate dates
        if issue_date and issue_date < timezone.now().date():
            raise ValidationError({
                'issue_date': _("Issue date cannot be in the past")
            })

        # Set due date based on due days if provided
        if due_days is not None and issue_date:
            cleaned_data['due_date'] = issue_date + timezone.timedelta(days=due_days)
        elif due_date and issue_date and due_date < issue_date:
            raise ValidationError({
                'due_date': _("Due date cannot be earlier than issue date")
            })

        # Validate items
        if not items_json:
            raise ValidationError(_("At least one item is required"))

        try:
            items = json.loads(items_json)
            if not items:
                raise ValidationError(_("At least one item is required"))
            
            # Validate each item
            for item in items:
                if not all(k in item for k in ('description', 'quantity', 'unit_price')):
                    raise ValidationError(_("Invalid item format"))
                if Decimal(str(item['quantity'])) <= 0:
                    raise ValidationError(_("Quantity must be greater than zero"))
                if Decimal(str(item['unit_price'])) < 0:
                    raise ValidationError(_("Unit price cannot be negative"))
                
        except json.JSONDecodeError:
            raise ValidationError(_("Invalid items data format"))
        except (TypeError, ValueError):
            raise ValidationError(_("Invalid number format in items"))

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if commit:
            instance.company = self.company
            instance.save()
            
            # Create invoice items
            items = json.loads(self.cleaned_data['items_json'])
            for item in items:
                InvoiceItem.objects.create(
                    invoice=instance,
                    description=item['description'],
                    quantity=Decimal(str(item['quantity'])),
                    unit_price=Decimal(str(item['unit_price'])),
                    tax_rate=Decimal(str(item.get('tax_rate', '0')))
                )

        return instance

class InvoiceUpdateForm(forms.ModelForm):
    """
    Form for updating an existing invoice.
    """
    class Meta:
        model = Invoice
        fields = ['status', 'due_date', 'notes', 'terms']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'terms': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            })
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        
        # Prevent status changes for paid invoices
        if (self.instance.status == 'PAID' and 
            status != 'PAID' and 
            not self.instance.is_refundable()):
            raise ValidationError({
                'status': _("Cannot change status of a paid invoice")
            })
            
        return cleaned_data

class RecurringInvoiceForm(forms.ModelForm):
    """
    Form for managing recurring invoice settings.
    """
    class Meta:
        model = Invoice
        fields = ['is_recurring', 'recurring_frequency', 'next_recurring_date']
        widgets = {
            'is_recurring': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'recurring_frequency': forms.Select(attrs={
                'class': 'form-select'
            }),
            'next_recurring_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            })
        }

    def clean(self):
        cleaned_data = super().clean()
        is_recurring = cleaned_data.get('is_recurring')
        recurring_frequency = cleaned_data.get('recurring_frequency')
        next_recurring_date = cleaned_data.get('next_recurring_date')

        if is_recurring:
            if not recurring_frequency:
                raise ValidationError({
                    'recurring_frequency': _("Frequency is required for recurring invoices")
                })
            if not next_recurring_date:
                raise ValidationError({
                    'next_recurring_date': _("Next date is required for recurring invoices")
                })
            if next_recurring_date <= timezone.now().date():
                raise ValidationError({
                    'next_recurring_date': _("Next recurring date must be in the future")
                })

        return cleaned_data

class InvoiceBulkActionForm(forms.Form):
    """
    Form for handling bulk actions on invoices.
    """
    ACTION_CHOICES = [
        ('send', _('Send to clients')),
        ('mark_sent', _('Mark as sent')),
        ('mark_paid', _('Mark as paid')),
        ('delete', _('Delete')),
    ]

    invoice_ids = forms.CharField(widget=forms.HiddenInput())
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean_invoice_ids(self):
        invoice_ids = self.cleaned_data['invoice_ids']
        try:
            ids = [int(id.strip()) for id in invoice_ids.split(',')]
            return ids
        except ValueError:
            raise ValidationError(_("Invalid invoice IDs format"))

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        invoice_ids = cleaned_data.get('invoice_ids', [])

        if action == 'delete':
            # Check if any of the selected invoices are paid
            paid_invoices = Invoice.objects.filter(
                id__in=invoice_ids,
                status='PAID'
            ).exists()
            if paid_invoices:
                raise ValidationError(_("Cannot delete paid invoices"))

        return cleaned_data