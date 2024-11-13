# expenseally/urls.py
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('dashboard', permanent=True)),  # Root path redirects to dashboard
    path('', include('financial_app.urls')),  # Includes all URLs from financial_app
]
