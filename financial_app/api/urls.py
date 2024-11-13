from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)
from . import views

router = DefaultRouter()
router.register(r'companies', views.CompanyViewSet, basename='company')
router.register(r'clients', views.ClientViewSet, basename='client')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'expenses', views.ExpenseViewSet, basename='expense')
router.register(r'expense-categories', views.ExpenseCategoryViewSet, basename='expense-category')
router.register(r'payments', views.PaymentRecordViewSet, basename='payment')
router.register(r'profile', views.UserProfileViewSet, basename='profile')

urlpatterns = [
    # JWT Authentication endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # API version 1 endpoints
    path('v1/', include([
        path('', include(router.urls)),
        
        # Custom analytics endpoints
        path('analytics/overview/', views.CompanyViewSet.as_view({
            'get': 'dashboard'
        }), name='analytics-overview'),
        
        # Reports endpoints
        path('reports/', include([
            path('profit-loss/', views.CompanyViewSet.as_view({
                'get': 'profit_loss_report'
            }), name='profit-loss-report'),
            path('cash-flow/', views.CompanyViewSet.as_view({
                'get': 'cash_flow_report'
            }), name='cash-flow-report'),
            path('tax-summary/', views.CompanyViewSet.as_view({
                'get': 'tax_summary_report'
            }), name='tax-summary-report'),
        ])),
        
        # Bulk operations
        path('invoices/bulk-send/', views.InvoiceViewSet.as_view({
            'post': 'bulk_send'
        }), name='invoice-bulk-send'),
        path('expenses/bulk-approve/', views.ExpenseViewSet.as_view({
            'post': 'bulk_approve'
        }), name='expense-bulk-approve'),
        
        # Export endpoints
        path('export/', include([
            path('invoices/', views.InvoiceViewSet.as_view({
                'get': 'export'
            }), name='export-invoices'),
            path('expenses/', views.ExpenseViewSet.as_view({
                'get': 'export'
            }), name='export-expenses'),
            path('clients/', views.ClientViewSet.as_view({
                'get': 'export'
            }), name='export-clients'),
        ])),
        
        # Dashboard widgets data
        path('widgets/', include([
            path('revenue-summary/', views.CompanyViewSet.as_view({
                'get': 'revenue_summary'
            }), name='widget-revenue-summary'),
            path('expense-summary/', views.CompanyViewSet.as_view({
                'get': 'expense_summary'
            }), name='widget-expense-summary'),
            path('outstanding-invoices/', views.CompanyViewSet.as_view({
                'get': 'outstanding_invoices'
            }), name='widget-outstanding-invoices'),
        ])),
        
        # Notification preferences
        path('notifications/preferences/', views.UserProfileViewSet.as_view({
            'get': 'notification_preferences',
            'put': 'update_notification_preferences'
        }), name='notification-preferences'),
    ])),

    # Documentation
    path('docs/', include([
        path('swagger/', views.SwaggerSchemaView.as_view(), name='swagger-ui'),
        path('redoc/', views.RedocSchemaView.as_view(), name='redoc'),
    ])),
]

# Additional configuration for router URLs
urlpatterns += [
    # Nested routes for related resources
    path('v1/companies/<int:company_pk>/', include([
        path('clients/', views.ClientViewSet.as_view({
            'get': 'list',
            'post': 'create'
        }), name='company-clients-list'),
        path('invoices/', views.InvoiceViewSet.as_view({
            'get': 'list',
            'post': 'create'
        }), name='company-invoices-list'),
        path('expenses/', views.ExpenseViewSet.as_view({
            'get': 'list',
            'post': 'create'
        }), name='company-expenses-list'),
    ])),
    
    path('v1/clients/<int:client_pk>/', include([
        path('invoices/', views.InvoiceViewSet.as_view({
            'get': 'list'
        }), name='client-invoices-list'),
        path('statement/', views.ClientViewSet.as_view({
            'get': 'statement'
        }), name='client-statement'),
    ])),
    
    path('v1/invoices/<int:invoice_pk>/', include([
        path('payments/', views.PaymentRecordViewSet.as_view({
            'get': 'list',
            'post': 'create'
        }), name='invoice-payments-list'),
        path('send/', views.InvoiceViewSet.as_view({
            'post': 'send'
        }), name='invoice-send'),
        path('void/', views.InvoiceViewSet.as_view({
            'post': 'void'
        }), name='invoice-void'),
    ])),
]

# Format suffixes
urlpatterns = format_suffix_patterns(urlpatterns, allowed=['json', 'csv', 'xlsx'])