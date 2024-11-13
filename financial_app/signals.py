from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Invoice, PaymentRecord, UserProfile, Client
from actstream import action

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
        action.send(instance, verb='joined ExpenseAlly')

@receiver(post_save, sender=Invoice)
def handle_invoice_status_change(sender, instance, created, **kwargs):
    if not created and instance.tracker.has_changed('status'):
        # Log the status change
        action.send(
            instance.company.owner,
            verb=f"changed invoice {instance.invoice_number} status to {instance.status}"
        )
        
        # Send notifications based on status
        if instance.status == 'SENT':
            # Send email to client
            context = {
                'invoice': instance,
                'client': instance.client,
                'company': instance.company
            }
            html_message = render_to_string(
                'financial_app/email/invoice_sent.html',
                context
            )
            send_mail(
                subject=f'New Invoice {instance.invoice_number} from {instance.company.name}',
                message='',
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.client.email],
                fail_silently=True
            )

@receiver(post_save, sender=PaymentRecord)
def handle_payment_record(sender, instance, created, **kwargs):
    if created and instance.status == 'COMPLETED':
        invoice = instance.invoice
        total_paid = sum(
            payment.amount 
            for payment in invoice.payments.filter(status='COMPLETED')
        )
        
        if total_paid >= invoice.total_amount:
            invoice.status = 'PAID'
            invoice.save()
            
        action.send(
            instance.invoice.company.owner,
            verb=f"recorded payment for invoice {instance.invoice.invoice_number}"
        )

@receiver(pre_save, sender=Client)
def handle_client_email_change(sender, instance, **kwargs):
    if instance.pk:
        old_instance = Client.objects.get(pk=instance.pk)
        if old_instance.email != instance.email:
            # Handle email change notifications if needed
            pass

@receiver(pre_delete, sender=Invoice)
def handle_invoice_deletion(sender, instance, **kwargs):
    # Log deletion
    action.send(
        instance.company.owner,
        verb=f"deleted invoice {instance.invoice_number}"
    )