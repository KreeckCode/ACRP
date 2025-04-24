from django import forms
from .models import BudgetRequest, Expenditure, Invoice, Asset, Vendor, RecurringExpense

class BudgetRequestForm(forms.ModelForm):
    """
    Form for creating or updating a BudgetRequest.
    Uses a datetime picker for the date_requested field.
    """
    class Meta:
        model = BudgetRequest
        # Include date_requested if you wish to allow editing it; otherwise, you could exclude it
        fields = ['department', 'amount_requested', 'justification', 'date_requested']
        widgets = {
            'date_requested': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }),
        }

class ExpenditureForm(forms.ModelForm):
    """
    Form for creating or updating an Expenditure.
    Uses a date picker for the date_spent field.
    """
    class Meta:
        model = Expenditure
        fields = ['description', 'department', 'amount_spent', 'category', 'date_spent']
        widgets = {
            'date_spent': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }

class InvoiceForm(forms.ModelForm):
    """
    Form for creating or updating an Invoice.
    Uses date pickers for due_date and date_sent fields.
    """
    class Meta:
        model = Invoice
        fields = ['vendor_name', 'description', 'amount_due', 'due_date', 'status', 'date_sent', 'file']
        widgets = {
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'date_sent': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }

class AssetForm(forms.ModelForm):
    """
    Form for creating or updating an Asset.
    Uses a date picker for the purchase_date field.
    """
    class Meta:
        model = Asset
        fields = ['asset_name', 'department', 'purchase_date', 'purchase_cost', 'depreciation_rate', 'condition']
        widgets = {
            'purchase_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }

class VendorForm(forms.ModelForm):
    """
    Form for creating or updating a Vendor.
    Uses a date picker for the contract_expiry_date field.
    """
    class Meta:
        model = Vendor
        fields = ['name', 'contact_email', 'phone_number', 'address', 'contract_file', 'contract_expiry_date']
        widgets = {
            'contract_expiry_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }

class RecurringExpenseForm(forms.ModelForm):
    """
    Form for creating or updating a RecurringExpense.
    Uses date pickers for the start_date and end_date fields.
    """
    class Meta:
        model = RecurringExpense
        fields = ['name', 'amount', 'frequency', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
        }
