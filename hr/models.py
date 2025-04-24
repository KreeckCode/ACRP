from django.db import models
from django.contrib.auth import get_user_model
from django.forms import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
User = get_user_model()

### Employee Profile Management ###



class EmployeeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="employee_profile")
    department = models.CharField(max_length=100, help_text="Department the employee belongs to.")
    job_title = models.CharField(max_length=100, help_text="The employee's job title.")
    date_of_hire = models.DateField(help_text="Date the employee was hired.")
    date_of_termination = models.DateField(null=True, blank=True, help_text="Date the employee was terminated (if applicable).")
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_subordinates')
    emergency_contact = models.CharField(max_length=100, blank=True, help_text="Emergency contact name.")
    emergency_contact_phone = models.CharField(max_length=20, blank=True, help_text="Emergency contact phone number.")
    active = models.BooleanField(default=True, help_text="Indicates whether the employee is currently active.")

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.job_title}"

    class Meta:
        verbose_name = "Employee Profile"
        verbose_name_plural = "Employee Profiles"
        ordering = ['user__last_name']


class EmployeeDocument(models.Model):
    """
    Represents various documents uploaded for an employee.
    """
    DOCUMENT_TYPES = [
        ('CONTRACT', 'Contract'),
        ('JOB_DESCRIPTION', 'Job Description'),
        ('HANDBOOK', 'Operational Handbook'),
        ('PERSONAL', 'Personal Document'),
        ('POLICY', 'Policy'),
        ('CERTIFICATE', 'Certificate'),
        ('PAYSLIP', 'Payslip'),
    ]
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES, help_text="Type of document being uploaded.")
    title = models.CharField(max_length=200, help_text="Title or name of the document.")
    file = models.FileField(upload_to="employee_documents/", help_text="Document file uploaded.")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="User who uploaded the document.")
    date_uploaded = models.DateField(auto_now_add=True, help_text="Date the document was uploaded.")
    is_editable_by_employee = models.BooleanField(default=False, help_text="Indicates if the employee can edit this document.")
    is_shared_with_employee = models.BooleanField(default=True, help_text="Indicates if the document is shared with the employee.")
    available_on_request = models.BooleanField(default=False, help_text="Indicates if the document is available upon request.")

    def __str__(self):
        return f"{self.employee.user.username} - {self.document_type}: {self.title}"

    class Meta:
        verbose_name = "Employee Document"
        verbose_name_plural = "Employee Documents"
        ordering = ['-date_uploaded']


class EmployeeWarning(models.Model):
    """
    Represents a disciplinary warning for an employee.
    """
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="warnings")
    title = models.CharField(max_length=200, help_text="Title of the disciplinary warning.")
    description = models.TextField(help_text="Detailed description of the warning.")
    document = models.FileField(upload_to="warnings/", help_text="Signed document for the warning.")
    start_date = models.DateField(help_text="Date the warning starts.")
    expiry_date = models.DateField(help_text="Expiry date of the warning.")
    status = models.CharField(max_length=20, default="Active", help_text="Status of the warning (e.g., Active, Expired).")

    def __str__(self):
        return f"Warning: {self.title} - {self.employee.user.username}"

    class Meta:
        verbose_name = "Employee Warning"
        verbose_name_plural = "Employee Warnings"
        ordering = ['-start_date']



import uuid
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.db.models.signals import post_save

User = get_user_model()

class DocumentFolder(models.Model):
    """
    Represents a folder that can contain subfolders and documents,
    much like Google Drive or OneDrive folders.
    """
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subfolders'
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_folders'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """
        So we can link to this folder's "contents" page easily.
        """
        return reverse('folder_detail', args=[self.id])


class HRDocumentStorage(models.Model):
    """
    Extends your existing model but adds a 'folder' reference,
    enabling hierarchical organization.
    """
    SECTION_CATEGORIES = [
        ('AUDITING', 'Auditing'),
        ('COMPLIANCE', 'Compliance'),
        ('EMPLOYMENT_TEMPLATES', 'Employment Templates'),
        ('OTHER', 'Other'),
    ]
    folder = models.ForeignKey(
        DocumentFolder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='documents'
    )
    section = models.CharField(
        max_length=100,
        choices=SECTION_CATEGORIES,
        help_text="Category/Section under which the document falls."
    )
    title = models.CharField(max_length=200, help_text="Title of the document.")
    file = models.FileField(upload_to="hr_documents/", help_text="HR document file uploaded.")
    expiry_date = models.DateField(null=True, blank=True, help_text="Expiry date of the document (if applicable).")
    date_uploaded = models.DateField(auto_now_add=True, help_text="Date the document was uploaded.")
    accessed_by = models.ManyToManyField(
        User,
        through="DocumentAccessLog",
        help_text="Users who have accessed this document."
    )

    def __str__(self):
        # Show folder name if available
        if self.folder:
            return f"[{self.folder.name}] {self.title}"
        return f"{self.section} - {self.title}"

    class Meta:
        verbose_name = "HR Document Storage"
        verbose_name_plural = "HR Document Storage"
        ordering = ['-date_uploaded']

    def get_absolute_url(self):
        # Direct link to "detail" or "download" view
        return reverse("document_download", args=[self.id])


class DocumentAccessLog(models.Model):
    """
    Tracks access to documents for security and transparency.
    """
    document = models.ForeignKey(
        HRDocumentStorage,
        on_delete=models.CASCADE,
        help_text="Document that was accessed."
    )
    accessed_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        help_text="User who accessed the document."
    )
    access_date = models.DateTimeField(auto_now_add=True, help_text="Date and time the document was accessed.")

    def __str__(self):
        return f"{self.accessed_by.username} accessed {self.document.title} on {self.access_date}"
    

#document request functionality
# models.py

class DocumentRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ('internal', 'Internal'),
        ('external', 'External'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    request_type = models.CharField(
        max_length=10, 
        choices=REQUEST_TYPE_CHOICES, 
        default='internal'
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='document_requests'
    )
    # For internal requests, the recipient will be a user in the organisation.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='document_requests_received'
    )
    # For external requests, basic details are required.
    external_recipient_name = models.CharField(max_length=255, blank=True)
    external_recipient_email = models.EmailField(blank=True)
    # Each employee has a folder where the received file will be stored.
    folder = models.ForeignKey(
        'DocumentFolder', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Folder to store the received file"
    )
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    request_date = models.DateTimeField(auto_now_add=True)
    response_date = models.DateTimeField(null=True, blank=True)
    attached_file = models.FileField(upload_to='document_requests/', null=True, blank=True)
    # New fields:
    max_file_size = models.PositiveIntegerField(
        default=10 * 1024 * 1024,  # default is 10MB in bytes
        help_text="Maximum allowed file size in bytes (default 10 MB)."
    )
    external_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    def __str__(self):
        return self.title

    def get_external_request_url(self, request=None):
        """
        Generates a URL that external recipients can use to attach the requested file.
        """
        rel_url = reverse('external_document_request_view', args=[str(self.external_token)])
        if request:
            return request.build_absolute_uri(rel_url)
        return rel_url


class DocumentShare(models.Model):
    """
    Represents a shareable link for a particular document,
    optionally with an expiry date or password protection, etc.
    """
    document = models.ForeignKey(
        HRDocumentStorage,
        on_delete=models.CASCADE,
        related_name="shares"
    )
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional. If set, the link expires after this datetime."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Share link for {self.document.title} ({self.token})"

    def get_share_url(self, request=None):
        """
        Return a full URL to access this shared document.
        If we have a 'request', we can build an absolute URL.
        """
        rel_url = reverse('document_share_view', args=[str(self.token)])
        if request:
            return request.build_absolute_uri(rel_url)
        return rel_url

    def is_expired(self):
        """
        Check if the current link has expired based on 'expires_at'.
        """
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at


class Payslip(models.Model):
    """
    Represents an employee's payslip.
    """
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="payslips")
    month = models.DateField(help_text="Month for which the payslip is generated.")
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, help_text="Employee's basic salary.")
    deductions = models.DecimalField(max_digits=10, decimal_places=2, help_text="Deductions from the salary (e.g., tax, pension).")
    bonuses = models.DecimalField(max_digits=10, decimal_places=2, default=0.0, help_text="Any bonuses added to the salary.")
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, help_text="Final net salary after deductions and bonuses.")
    document = models.FileField(upload_to="payslips/", help_text="Payslip file uploaded.")

    def __str__(self):
        return f"{self.employee.user.username} Payslip for {self.month}"

    class Meta:
        verbose_name = "Payslip"
        verbose_name_plural = "Payslips"
        ordering = ['-month']


class LeaveBalance(models.Model):
    """
    Tracks the leave balance and cycle for an employee.
    """
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE, related_name="leave_balance")
    total_leave_days = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=15.0,  # Default allocation of leave days
        help_text="Total leave days allocated for the leave cycle."
    )
    leave_days_remaining = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=15.0,  # Default remaining leave days
        help_text="Remaining leave days available for the leave cycle."
    )
    leave_cycle_start = models.DateField(help_text="Start date of the leave cycle.")
    leave_cycle_end = models.DateField(help_text="End date of the leave cycle.")

    def carry_over_days(self):
        """
        Carries over unused leave days to the next cycle.
        """
        if self.leave_days_remaining > 0:
            self.total_leave_days += self.leave_days_remaining
            self.leave_days_remaining = 0
            self.save()

    def __str__(self):
        return f"{self.employee.user.username} - {self.leave_days_remaining} days remaining"

    class Meta:
        verbose_name = "Leave Balance"
        verbose_name_plural = "Leave Balances"



class LeaveType(models.Model):
    """
    Represents different types of leave that employees can request.
    """
    name = models.CharField(max_length=100, unique=True, help_text="Name of the leave type (e.g., Annual Leave).")
    description = models.TextField(null=True, blank=True, help_text="Description of the leave type.")
    default_allocation = models.DecimalField(max_digits=5, decimal_places=2, default=0.0, help_text="Default allocation of days for this leave type.")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Leave Type"
        verbose_name_plural = "Leave Types"


class LeaveRequest(models.Model):
    """
    Tracks leave requests submitted by employees.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('DECLINED', 'Declined'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name="leave_requests")
    start_date = models.DateField(help_text="Start date of the leave.")
    end_date = models.DateField(help_text="End date of the leave.")
    total_days = models.DecimalField(max_digits=5, decimal_places=2, help_text="Total days of leave requested.", default=0.0)
    reason = models.TextField(help_text="Reason for the leave request.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', help_text="Status of the leave request.")
    hr_comment = models.TextField(null=True, blank=True, help_text="HR's comment on the leave request.")
    date_requested = models.DateField(default=timezone.now,  help_text="Date the leave was requested.")
    date_updated = models.DateField(default=timezone.now, help_text="Date the leave request was last updated.")

    def approve(self, hr_comment=None):
        """
        Approve the leave request and adjust the employee's leave balance.
        """
        if self.status == 'PENDING':
            leave_balance = self.employee.leave_balance
            if leave_balance.leave_days_remaining >= self.total_days:
                self.status = 'APPROVED'
                self.hr_comment = hr_comment
                leave_balance.leave_days_remaining -= self.total_days
                leave_balance.save()
                self.save()
            else:
                raise ValidationError("Insufficient leave balance.")

    def decline(self, hr_comment):
        """
        Decline the leave request with a comment.
        """
        if self.status == 'PENDING':
            self.status = 'DECLINED'
            self.hr_comment = hr_comment
            self.save()

    def __str__(self):
        return f"{self.employee.user.username} - {self.leave_type.name}: {self.status}"

    class Meta:
        verbose_name = "Leave Request"
        verbose_name_plural = "Leave Requests"
        ordering = ['-date_requested']

@receiver(post_save, sender=EmployeeProfile)
def create_leave_balance(sender, instance, created, **kwargs):
    if created:
        LeaveBalance.objects.create(
            employee=instance,
            total_leave_days=15.0,  # Default leave days
            leave_days_remaining=15.0,  # Default remaining days
            leave_cycle_start=timezone.now().date(),
            leave_cycle_end=(timezone.now() + timezone.timedelta(days=365)).date(),
        )

from django.contrib import admin
from .models import LeaveBalance

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'total_leave_days', 'leave_days_remaining', 'leave_cycle_start', 'leave_cycle_end')
    list_filter = ('employee__department',)
    search_fields = ('employee__user__username', 'employee__user__first_name', 'employee__user__last_name')
    readonly_fields = ('employee',)
    fieldsets = (
        (None, {
            'fields': ('employee', 'total_leave_days', 'leave_days_remaining', 'leave_cycle_start', 'leave_cycle_end')
        }),
    )

