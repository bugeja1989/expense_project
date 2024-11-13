from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from datetime import datetime
from ..models import (
    Company, Client, Invoice, InvoiceItem, 
    Expense, ExpenseCategory, UserProfile, 
    PaymentRecord
)
from .serializers import (
    CompanySerializer, ClientSerializer, InvoiceSerializer,
    ExpenseSerializer, ExpenseCategorySerializer, UserProfileSerializer,
    PaymentRecordSerializer
)
from ..services.report_service import ReportService
from ..services.analytics_service import AnalyticsService

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Company.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def dashboard(self, request, pk=None):
        company = self.get_object()
        analytics = AnalyticsService.get_business_overview(company)
        return Response(analytics)

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email', 'phone']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        return Client.objects.filter(company__owner=self.request.user)

    def perform_create(self, serializer):
        company = get_object_or_404(Company, owner=self.request.user)
        serializer.save(company=company)

    @action(detail=True, methods=['get'])
    def invoices(self, request, pk=None):
        client = self.get_object()
        invoices = Invoice.objects.filter(client=client)
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        client = self.get_object()
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        statement = ReportService.generate_client_statement(client, start_date, end_date)
        return Response(statement)

class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['invoice_number', 'client__name']
    ordering_fields = ['issue_date', 'due_date', 'total_amount']

    def get_queryset(self):
        queryset = Invoice.objects.filter(company__owner=self.request.user)
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def perform_create(self, serializer):
        company = get_object_or_404(Company, owner=self.request.user)
        serializer.save(company=company)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        invoice = self.get_object()
        try:
            # Use your invoice service to send the invoice
            invoice.status = 'SENT'
            invoice.save()
            return Response({'status': 'Invoice sent successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        invoice = self.get_object()
        serializer = PaymentRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                invoice=invoice,
                processed_by=request.user
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        invoice = self.get_object()
        reason = request.data.get('reason')
        if not reason:
            return Response(
                {'error': 'Reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if invoice.status == 'PAID':
            return Response(
                {'error': 'Cannot void a paid invoice'},
                status=status.HTTP_400_BAD_REQUEST
            )

        invoice.status = 'CANCELLED'
        invoice.notes += f"\nVoided on {timezone.now()}: {reason}"
        invoice.save()
        return Response({'status': 'Invoice voided successfully'})

class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]
    queryset = ExpenseCategory.objects.all()

class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['description', 'vendor']
    ordering_fields = ['date', 'amount']

    def get_queryset(self):
        queryset = Expense.objects.filter(company__owner=self.request.user)
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category_id=category)
        return queryset

    def perform_create(self, serializer):
        company = get_object_or_404(Company, owner=self.request.user)
        serializer.save(
            company=company,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        expense = self.get_object()
        if expense.approved_by:
            return Response(
                {'error': 'Expense already approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        expense.approved_by = request.user
        expense.approval_date = timezone.now()
        expense.save()
        return Response({'status': 'Expense approved successfully'})

class PaymentRecordViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentRecordSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return PaymentRecord.objects.filter(
            invoice__company__owner=self.request.user
        )

    def perform_create(self, serializer):
        serializer.save(processed_by=self.request.user)

class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def update_preferences(self, request, pk=None):
        profile = self.get_object()
        preferences = request.data.get('notification_preferences', {})
        profile.notification_preferences = preferences
        profile.save()
        return Response({'status': 'Preferences updated successfully'})