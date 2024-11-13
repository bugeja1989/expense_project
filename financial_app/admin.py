from django.contrib import admin
from .models import Company, Client, Invoice, InvoiceItem, Expense  # Ensure InvoiceItem is correctly imported

admin.site.register(Company)
admin.site.register(Client)
admin.site.register(Invoice)
admin.site.register(InvoiceItem)
admin.site.register(Expense)
