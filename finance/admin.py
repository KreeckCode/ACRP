from django.contrib import admin
from .models import BudgetRequest, Expenditure, FinancialReport, Invoice, Vendor, Asset

@admin.register(BudgetRequest)
class BudgetRequestAdmin(admin.ModelAdmin):
    list_display = ('department', 'amount_requested', 'status', 'date_requested', 'requested_by')

@admin.register(Expenditure)
class ExpenditureAdmin(admin.ModelAdmin):
    list_display = ('department', 'amount_spent', 'category', 'date_spent', 'recorded_by')

@admin.register(FinancialReport)
class FinancialReportAdmin(admin.ModelAdmin):
    list_display = ('report_name', 'date_generated', 'generated_by')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('vendor_name', 'amount_due', 'due_date', 'status')

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'contract_expiry_date')

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_name', 'department', 'purchase_date', 'purchase_cost')
