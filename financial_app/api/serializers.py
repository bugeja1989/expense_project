from rest_framework import serializers
from django.contrib.auth.models import User
from ..models import (
    Company, Client, Invoice, InvoiceItem, 
    Expense, ExpenseCategory, UserProfile, 
    PaymentRecord
)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name')
        read_only_fields = ('id',)

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ('id', 'user', 'role', 'language', 'phone', 
                 'notification_preferences', 'created_at')
        read_only_fields = ('id', 'created_at')

class CompanySerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    
    class Meta:
        model = Company
        fields = ('id', 'name', 'owner', 'vat_number', 'registration_number',
                 'preferred_currency', 'logo', 'address', 'phone', 'email',
                 'website', 'tax_number', 'bank_account', 'bank_name',
                 'swift_code', 'iban', 'default_payment_terms',
                 'invoice_notes_template', 'invoice_footer', 'created_at')
        read_only_fields = ('id', 'owner', 'created_at')

    def validate_logo(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB limit
            raise serializers.ValidationError("Logo file size cannot exceed 5MB.")
        return value

class ClientSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    outstanding_balance = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    
    class Meta:
        model = Client
        fields = ('id', 'company', 'name', 'email', 'phone', 'address',
                 'vat_number', 'contact_person', 'notes', 'payment_terms',
                 'credit_limit', 'is_active', 'created_at', 'outstanding_balance')
        read_only_fields = ('id', 'company', 'created_at')

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['outstanding_balance'] = instance.get_outstanding_balance()
        return representation

class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ('id', 'description', 'quantity', 'unit_price', 
                 'tax_rate', 'total')
        read_only_fields = ('id', 'total')

class InvoiceSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    client = ClientSerializer(read_only=True)
    items = InvoiceItemSerializer(many=True, required=False)
    client_id = serializers.PrimaryKeyRelatedField(
        source='client',
        queryset=Client.objects.all(),
        write_only=True
    )
    
    class Meta:
        model = Invoice
        fields = ('id', 'company', 'client', 'client_id', 'invoice_number',
                 'status', 'issue_date', 'due_date', 'subtotal', 'tax_rate',
                 'tax_amount', 'total_amount', 'amount_paid', 'notes', 'terms',
                 'footer', 'reference_number', 'items', 'is_recurring',
                 'recurring_frequency', 'next_recurring_date', 'created_at')
        read_only_fields = ('id', 'company', 'invoice_number', 'subtotal',
                          'tax_amount', 'total_amount', 'amount_paid', 'created_at')

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        invoice = Invoice.objects.create(**validated_data)
        
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item_data)
        
        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', [])
        
        # Update invoice fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update invoice items
        instance.items.all().delete()
        for item_data in items_data:
            InvoiceItem.objects.create(invoice=instance, **item_data)
        
        return instance

class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ('id', 'name', 'description', 'is_active', 'parent')
        read_only_fields = ('id',)

class ExpenseSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    category = ExpenseCategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source='category',
        queryset=ExpenseCategory.objects.all(),
        write_only=True
    )
    created_by = UserSerializer(read_only=True)
    approved_by = UserSerializer(read_only=True)
    
    class Meta:
        model = Expense
        fields = ('id', 'company', 'category', 'category_id', 'amount', 'date',
                 'description', 'receipt', 'vendor', 'reference_number',
                 'payment_method', 'is_recurring', 'recurring_frequency',
                 'next_recurring_date', 'tax_deductible', 'created_by',
                 'approved_by', 'approval_date', 'tags', 'notes', 'created_at')
        read_only_fields = ('id', 'company', 'created_by', 'approved_by',
                          'approval_date', 'created_at')

    def validate_receipt(self, value):
        if value and value.size > 5 * 1024 * 1024:  # 5MB limit
            raise serializers.ValidationError("Receipt file size cannot exceed 5MB.")
        return value

class PaymentRecordSerializer(serializers.ModelSerializer):
    invoice = InvoiceSerializer(read_only=True)
    invoice_id = serializers.PrimaryKeyRelatedField(
        source='invoice',
        queryset=Invoice.objects.all(),
        write_only=True
    )
    processed_by = UserSerializer(read_only=True)
    
    class Meta:
        model = PaymentRecord
        fields = ('id', 'invoice', 'invoice_id', 'amount', 'payment_date',
                 'payment_method', 'status', 'transaction_id', 'reference_number',
                 'notes', 'processed_by', 'processing_fee', 'created_at')
        read_only_fields = ('id', 'processed_by', 'created_at')

    def validate(self, data):
        if data['amount'] > data['invoice'].get_balance_due():
            raise serializers.ValidationError(
                "Payment amount cannot exceed invoice balance."
            )
        return data