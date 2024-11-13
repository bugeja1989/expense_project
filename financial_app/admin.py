from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    Company, Client, Invoice, InvoiceItem, 
    Expense, ExpenseCategory, UserProfile, 
    PaymentRecord
)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'preferred_currency', 'created_at')
    list_filter = ('preferred_currency', 'created_at')
    search_fields = ('name', 'owner__username')
    date_hierarchy = 'created_at'

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'email', 'phone', 'created_at')
    list_filter = ('company', 'created_at')
    search_fields = ('name', 'email', 'phone')
    date_hierarchy = 'created_at'

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'company', 'client', 'total_amount', 
                   'status', 'issue_date', 'due_date')
    list_filter = ('status', 'issue_date', 'due_date', 'company')
    search_fields = ('invoice_number', 'client__name')
    date_hierarchy = 'issue_date'
    inlines = [InvoiceItemInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.filter(company__owner=request.user)
        return qs

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('company', 'category', 'amount', 'date', 'receipt_preview')
    list_filter = ('category', 'date', 'company')
    search_fields = ('description',)
    date_hierarchy = 'date'
    
    def receipt_preview(self, obj):
        if obj.receipt:
            return format_html('<a href="{}" target="_blank">View Receipt</a>', 
                             obj.receipt.url)
        return "No receipt"
    receipt_preview.short_description = 'Receipt'

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'language', 'created_at')
    list_filter = ('role', 'language', 'created_at')
    search_fields = ('user__username', 'user__email')
    date_hierarchy = 'created_at'

@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_date', 'payment_method', 'status')
    list_filter = ('payment_method', 'status', 'payment_date')
    search_fields = ('invoice__invoice_number',)
    date_hierarchy = 'payment_date'

# Custom admin site configuration
admin.site.site_header = 'ExpenseAlly Administration'
admin.site.site_title = 'ExpenseAlly Admin Portal'
admin.site.index_title = 'Welcome to ExpenseAlly Administration'