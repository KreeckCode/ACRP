from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Budget Requests
    path('budget-requests/', views.budget_request_list, name='budget_request_list'),
    path('budget-requests/submit/', views.submit_budget_request, name='submit_budget_request'),
    path('budget-requests/<int:pk>/approve/', views.approve_budget_request, name='approve_budget_request'),
    path('budget-requests/<int:pk>/reject/', views.reject_budget_request, name='reject_budget_request'),
    path('budget-request/<int:pk>/', views.budget_request_detail, name='budget_request_detail'),
    path('my-budget-requests/', views.my_budget_request_list, name='my_budget_request_list'),

    # Expenditure URLs
    path('expenditures/', views.expenditure_list, name='expenditure_list'),
    path('expenditures/add/', views.add_expenditure, name='add_expenditure'),
    path('expenditures/<int:pk>/', views.expenditure_detail, name='expenditure_detail'),
    path('expenditures/<int:pk>/update/', views.update_expenditure, name='update_expenditure'),
    path('expenditures/<int:pk>/delete/', views.delete_expenditure, name='delete_expenditure'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/add/', views.add_invoice, name='add_invoice'),
    path('invoices/<int:pk>/update/', views.update_invoice, name='update_invoice'),
    path('invoices/<int:pk>/delete/', views.delete_invoice, name='delete_invoice'),

    # Vendors
    path('vendors/', views.vendor_list, name='vendor_list'),
    path('vendors/add/', views.add_vendor, name='add_vendor'),
    path('vendors/<int:pk>/update/', views.update_vendor, name='update_vendor'),
    path('vendors/<int:pk>/delete/', views.delete_vendor, name='delete_vendor'),

    # Assets
    path('assets/', views.asset_list, name='asset_list'),
    path('assets/add/', views.add_asset, name='add_asset'),
    path('assets/<int:pk>/update/', views.update_asset, name='update_asset'),
    path('assets/<int:pk>/delete/', views.delete_asset, name='delete_asset'),
    path('company-assets/', views.company_asset_list, name='company_asset_list'),

    # Recurring Expenses
    path('recurring-expenses/', views.recurring_expense_list, name='recurring_expense_list'),
    path('recurring-expenses/add/', views.add_recurring_expense, name='add_recurring_expense'),
]
