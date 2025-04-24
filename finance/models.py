from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# 1. Budget Request and Approval System
class BudgetRequest(models.Model):
    REQUEST_STATUS = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected')
    ]

    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="budget_requests")
    department = models.CharField(max_length=100)
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    justification = models.TextField()
    status = models.CharField(max_length=10, choices=REQUEST_STATUS, default='PENDING')
    date_requested = models.DateTimeField(default=timezone.now)
    date_processed = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_requests")

    def __str__(self):
        return f"{self.department} - {self.amount_requested} - {self.status}"

    class Meta:
        permissions = [
            ("approve_budget_request", "Can approve or reject budget requests")
        ]


# 2. Expenditure Tracking and Analysis
class Expenditure(models.Model):
    class Category(models.TextChoices):
        SALARY = 'SALARY', 'Salary'
        SUPPLIES = 'SUPPLIES', 'Supplies'
        TRAVEL = 'TRAVEL', 'Travel'
        EQUIPMENT = 'EQUIPMENT', 'Equipment'
        OTHER = 'OTHER', 'Other'

    description = models.CharField(max_length=200)
    department = models.CharField(max_length=100)
    amount_spent = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=50, choices=Category.choices)
    date_spent = models.DateField(default=timezone.now)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="expenditures")

    def __str__(self):
        return f"{self.department} - {self.amount_spent} on {self.category}"


# 3. Financial Reporting
class FinancialReport(models.Model):
    report_name = models.CharField(max_length=100)
    date_generated = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="financial_reports")
    file = models.FileField(upload_to='financial_reports/')

    def __str__(self):
        return self.report_name


# 4. Automated Invoice Management
class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SENT = 'SENT', 'Sent'
        PAID = 'PAID', 'Paid'
        OVERDUE = 'OVERDUE', 'Overdue'

    vendor_name = models.CharField(max_length=100)
    description = models.TextField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    date_sent = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to='invoices/', blank=True, null=True)

    def __str__(self):
        return f"Invoice to {self.vendor_name} - {self.amount_due} - {self.status}"


# 5. Asset and Inventory Management
class Asset(models.Model):
    asset_name = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)
    depreciation_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Depreciation rate per year in percentage")
    condition = models.CharField(max_length=100, blank=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.asset_name} - {self.department}"

    def calculate_depreciation(self):
        """Calculates current depreciated value of the asset."""
        years_owned = timezone.now().year - self.purchase_date.year
        depreciation_value = (self.purchase_cost * self.depreciation_rate / 100) * years_owned
        return max(self.purchase_cost - depreciation_value, 0)


# 6. Vendor and Supplier Management
class Vendor(models.Model):
    name = models.CharField(max_length=100)
    contact_email = models.EmailField()
    phone_number = models.CharField(max_length=20)
    address = models.TextField()
    contract_file = models.FileField(upload_to='vendor_contracts/', blank=True, null=True)
    contract_expiry_date = models.DateField()

    def __str__(self):
        return self.name


class RecurringExpense(models.Model):
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(max_length=20, choices=[
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
        ('YEARLY', 'Yearly'),
    ])
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="recurring_expenses")

    def __str__(self):
        return f"{self.name} - {self.amount} ({self.frequency})"
