# financial_app/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('invoices/create/', views.create_invoice, name='create_invoice'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('clients/', views.client_list, name='client_list'),
    path('expenses/summary/', views.expense_summary, name='expense_summary'),
    path('upload_receipt/', views.upload_receipt, name='upload_receipt'),
    path('signup/', views.signup, name='signup'),  # Add signup URL pattern here
]
