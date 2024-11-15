# File: financial_app/views.py

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta

from .models import (
    Company, Client, Invoice, InvoiceItem, 
    Expense, ExpenseCategory, UserProfile, 
    PaymentRecord
)
from .serializers import (
    CompanySerializer, ClientSerializer, InvoiceSerializer,
    ExpenseSerializer, ExpenseCategorySerializer, UserProfileSerializer,
    PaymentRecordSerializer
)
from .services.report_service import ReportService
from .services.analytics_service import AnalyticsService

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

@login_required
def dashboard(request):
    """Main dashboard view combining all analytics"""
    company = request.user.company
    
    context = {
        'overview': AnalyticsService.get_business_overview(company),
        'recent_transactions': AnalyticsService.get_recent_transactions(company),
        'expense_breakdown': AnalyticsService.get_expense_breakdown(company),
        'cash_flow': AnalyticsService.get_cash_flow_trend(company),
        'payment_stats': AnalyticsService.get_payment_statistics(company)
    }
    
    return render(request, 'financial_app/dashboard/index.html', context)

@login_required
def dashboard_api_overview(request):
    """API endpoint for dashboard overview data"""
    company = request.user.company
    timeframe = request.GET.get('timeframe', 'month')
    overview = AnalyticsService.get_business_overview(company)
    return JsonResponse(overview)

@login_required
def dashboard_api_transactions(request):
    """API endpoint for recent transactions"""
    company = request.user.company
    limit = int(request.GET.get('limit', 10))
    transactions = AnalyticsService.get_recent_transactions(company, limit=limit)
    return JsonResponse({'transactions': list(transactions)})

@login_required
def generate_report(request):
    """Generate a comprehensive business report"""
    company = request.user.company
    report_type = request.GET.get('type', 'summary')
    
    try:
        start_date = datetime.strptime(request.GET.get('start_date', ''), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.GET.get('end_date', ''), '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

    if report_type == 'pdf':
        report = ReportService.generate_pdf_report(company, start_date, end_date)
        response = HttpResponse(report, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="report.pdf"'
        return response
    else:
        report = ReportService.generate_business_report(company, start_date, end_date)
        return JsonResponse(report)

class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return Company.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get comprehensive analytics for a company"""
        company = self.get_object()
        timeframe = request.query_params.get('timeframe', 'month')
        
        analytics = {
            'overview': AnalyticsService.get_business_overview(company),
            'expense_breakdown': AnalyticsService.get_expense_breakdown(company),
            'cash_flow': AnalyticsService.get_cash_flow_trend(company),
            'payment_stats': AnalyticsService.get_payment_statistics(company)
        }
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
        status_param = self.request.query_params.get('status', None)
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset

    def perform_create(self, serializer):
        company = get_object_or_404(Company, owner=self.request.user)
        serializer.save(company=company)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        invoice = self.get_object()
        try:
            invoice.status = 'SENT'
            invoice.save()
            return Response({'status': 'Invoice sent successfully'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        invoice = self.get_object()
        serializer = PaymentRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(invoice=invoice, processed_by=request.user)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        invoice = self.get_object()
        reason = request.data.get('reason')
        if not reason:
            return Response({'error': 'Reason is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if invoice.status == 'PAID':
            return Response({'error': 'Cannot void a paid invoice'}, status=status.HTTP_400_BAD_REQUEST)

        invoice.status = 'CANCELLED'
        invoice.notes += f"\nVoided on {timezone.now()}: {reason}"
        invoice.save()
        return Response({'status': 'Invoice voided successfully'})

class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ExpenseCategory.objects.filter(company__owner=self.request.user)

    def perform_create(self, serializer):
        company = get_object_or_404(Company, owner=self.request.user)
        serializer.save(company=company)

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
        serializer.save(company=company, created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        expense = self.get_object()
        if expense.approved_by:
            return Response({'error': 'Expense already approved'}, status=status.HTTP_400_BAD_REQUEST)
        
        expense.approved_by = request.user
        expense.approval_date = timezone.now()
        expense.save()
        return Response({'status': 'Expense approved successfully'})

class PaymentRecordViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentRecordSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return PaymentRecord.objects.filter(invoice__company__owner=self.request.user)

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