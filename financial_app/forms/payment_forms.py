from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..models import PaymentRecord, Invoice
from decimal import Decimal

class PaymentRecordForm(forms.ModelForm):
    """
    Form for recording payments for invoices.
    """
    send_receipt = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text=_("Send payment receipt to client")
    )

    class Meta:
        model = PaymentRecord
        fields = [
            'amount', 'payment_date', 'payment_method', 
            'transaction_id', 'reference_number', 'notes'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'payment_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'payment_method': forms.Select(attrs={
                'class': 'form-select'
            }),
            'transaction_id': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'reference_number': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            })
        }

    def __init__(self, *args, **kwargs):
        self.invoice = kwargs.pop('invoice', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.invoice:
            # Set initial amount to remaining balance
            self.fields['amount'].initial = self.invoice.get_balance_due()
            self.fields['amount'].widget.attrs['max'] = self.invoice.get_balance_due()

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.invoice:
            balance_due = self.invoice.get_balance_due()
            if amount > balance_due:
                raise ValidationError(
                    _("Payment amount (%(amount)s) cannot exceed balance due (%(balance)s)"),
                    params={'amount': amount, 'balance': balance_due},
                )
            if amount <= 0:
                raise ValidationError(_("Payment amount must be greater than zero"))
        return amount

    def clean_payment_date(self):
        payment_date = self.cleaned_data['payment_date']
        if payment_date > timezone.now().date():
            raise ValidationError(_("Payment date cannot be in the future"))
        if self.invoice and payment_date < self.invoice.issue_date:
            raise ValidationError(_("Payment date cannot be before invoice issue date"))
        return payment_date

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.invoice = self.invoice
        instance.processed_by = self.user
        instance.status = 'COMPLETED'
        
        if commit:
            instance.save()
            
            # Update invoice paid amount and status
            self.invoice.amount_paid = (
                self.invoice.amount_paid or Decimal('0')
            ) + instance.amount
            
            if self.invoice.amount_paid >= self.invoice.total_amount:
                self.invoice.status = 'PAID'
            elif self.invoice.amount_paid > 0:
                self.invoice.status = 'PARTIALLY_PAID'
            
            self.invoice.save()
            
            # Send receipt if requested
            if self.cleaned_data.get('send_receipt'):
                instance.send_receipt()
        
        return instance

class BulkPaymentForm(forms.Form):
    """
    Form for recording payments for multiple invoices at once.
    """
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    payment_method = forms.ChoiceField(
        choices=PaymentRecord.PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )
    reference_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control'
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3
        })
    )
    send_receipts = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    def clean_payment_date(self):
        payment_date = self.cleaned_data['payment_date']
        if payment_date > timezone.now().date():
            raise ValidationError(_("Payment date cannot be in the future"))
        return payment_date

class PaymentRefundForm(forms.ModelForm):
    """
    Form for recording payment refunds.
    """
    refund_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3
        }),
        help_text=_("Provide a reason for the refund")
    )
    
    notify_client = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    class Meta:
        model = PaymentRecord
        fields = ['amount', 'refund_reason']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            })
        }

    def __init__(self, *args, **kwargs):
        self.payment = kwargs.pop('payment', None)
        super().__init__(*args, **kwargs)
        
        if self.payment:
            self.fields['amount'].initial = self.payment.amount
            self.fields['amount'].widget.attrs['max'] = self.payment.amount

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.payment and amount > self.payment.amount:
            raise ValidationError(
                _("Refund amount cannot exceed original payment amount (%(amount)s)"),
                params={'amount': self.payment.amount}
            )
        return amount

    def save(self, commit=True):
        refund = PaymentRecord.objects.create(
            invoice=self.payment.invoice,
            amount=-self.cleaned_data['amount'],
            payment_date=timezone.now().date(),
            payment_method=self.payment.payment_method,
            status='REFUNDED',
            notes=f"Refund for payment #{self.payment.id}. "
                  f"Reason: {self.cleaned_data['refund_reason']}",
            processed_by=self.payment.processed_by,
            reference_number=f"REF-{self.payment.reference_number}"
        )
        
        # Update invoice status and amount paid
        invoice = self.payment.invoice
        invoice.amount_paid -= self.cleaned_data['amount']
        if invoice.amount_paid <= 0:
            invoice.status = 'SENT'
        elif invoice.amount_paid < invoice.total_amount:
            invoice.status = 'PARTIALLY_PAID'
        invoice.save()
        
        # Notify client if requested
        if self.cleaned_data['notify_client']:
            refund.send_refund_notification()
        
        return refund