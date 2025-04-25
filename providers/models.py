from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
User = get_user_model()


class Provider(models.Model):
    code                = models.CharField(max_length=30, unique=True)
    trade_name          = models.CharField(max_length=100)
    legal_name          = models.CharField(max_length=200)
    registration_number = models.CharField(max_length=50)
    vat_number          = models.CharField(max_length=50, blank=True, null=True)
    qcto_provider_code  = models.CharField(max_length=50, blank=True, null=True)

    # Address
    address_line1 = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True, null=True)
    city          = models.CharField(max_length=100)
    province      = models.CharField(max_length=100)
    postal_code   = models.CharField(max_length=20)
    country       = models.CharField(max_length=100, default='South Africa')

    # Contact
    phone   = models.CharField(max_length=50)
    email   = models.EmailField()
    website = models.URLField(blank=True, null=True)

    # Status
    class StatusChoices(models.TextChoices):
        ACTIVE    = 'ACTIVE', 'Active'
        INACTIVE  = 'INACTIVE', 'Inactive'
        SUSPENDED = 'SUSPENDED', 'Suspended'
    status     = models.CharField(max_length=10, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, related_name='providers_created',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    updated_by = models.ForeignKey(
        User, related_name='providers_updated',
        on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.trade_name} ({self.code})"


class ProviderAccreditation(models.Model):
    provider             = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='accreditations')
    code                 = models.CharField(max_length=30)
    name                 = models.CharField(max_length=100)
    description          = models.TextField(blank=True, null=True)
    accreditation_number = models.CharField(max_length=50)
    accrediting_body     = models.CharField(max_length=100)
    association          = models.CharField(max_length=100, blank=True, null=True)
    start_date           = models.DateField()
    expiry_date          = models.DateField()
    status               = models.CharField(
        max_length=10,
        choices=[
            ('ACTIVE','Active'),
            ('PROBATION','Probation'),
            ('EXPIRED','Expired'),
            ('WITHDRAWN','Withdrawn'),
        ],
        default='ACTIVE'
    )
    certificate_file     = models.FileField(upload_to='provider/accreditations/')

    def __str__(self):
        return f"{self.provider.code} – {self.name}"


class Qualification(models.Model):
    provider               = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='qualifications')
    name                   = models.CharField(max_length=200)
    description            = models.TextField()
    saqa_id                = models.CharField(max_length=50, blank=True, null=True)
    qcto_id                = models.CharField(max_length=50, blank=True, null=True)
    credit_value           = models.DecimalField(max_digits=5, decimal_places=2)
    total_hours            = models.PositiveIntegerField()
    level                  = models.PositiveSmallIntegerField(choices=[(i,i) for i in range(1,11)])
    qualification_document = models.FileField(upload_to='provider/qualifications/', blank=True, null=True)
    created_at             = models.DateTimeField(auto_now_add=True)
    updated_at             = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.provider.code})"


class QualificationModule(models.Model):
    qualification = models.ForeignKey(Qualification, on_delete=models.CASCADE, related_name='modules')
    code          = models.CharField(max_length=30)
    name          = models.CharField(max_length=200)
    description   = models.TextField(blank=True, null=True)
    credits       = models.DecimalField(max_digits=5, decimal_places=2)
    hours         = models.PositiveIntegerField()
    order         = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('qualification','code')
        ordering        = ['order']

    def __str__(self):
        return f"{self.code}: {self.name}"


class ProviderUserProfile(models.Model):
    class RoleChoices(models.TextChoices):
        CENTER_ADMIN         = 'CENTER_ADMIN', 'Center Administrator'
        INTERNAL_FACILITATOR = 'INTERNAL_FACILITATOR', 'Internal Facilitator'

    user            = models.OneToOneField(User, on_delete=models.CASCADE)
    provider        = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='users')
    role            = models.CharField(max_length=20, choices=RoleChoices.choices)
    phone           = models.CharField(max_length=50, blank=True, null=True)
    alternate_email = models.EmailField(blank=True, null=True)
    bio             = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name} | {self.get_role_display()}"


class AssessorProfile(models.Model):
    user              = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    provider          = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='assessors')
    first_name        = models.CharField(max_length=50)
    last_name         = models.CharField(max_length=50)
    class IDType(models.TextChoices):
        ID       = 'ID', 'ID'
        PASSPORT = 'PASSPORT', 'Passport'
        OTHER    = 'OTHER', 'Other'
    id_type           = models.CharField(max_length=20, choices=IDType.choices)
    id_number         = models.CharField(max_length=50, unique=True)
    date_of_birth     = models.DateField()
    contact_phone     = models.CharField(max_length=50)
    contact_email     = models.EmailField()
    has_system_access = models.BooleanField(default=False)
    status            = models.CharField(
        max_length=10,
        choices=[('ACTIVE','Active'),('INACTIVE','Inactive')],
        default='ACTIVE'
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.provider.code})"


class ProviderDocument(models.Model):
    provider     = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='documents')
    name         = models.CharField(max_length=100)
    file         = models.FileField(upload_to='provider/documents/')
    uploaded_at  = models.DateTimeField(auto_now_add=True)
    status       = models.CharField(
        max_length=10,
        choices=[('PENDING','Pending'),('APPROVED','Approved'),('REJECTED','Rejected')],
        default='PENDING'
    )
    reviewed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.provider.code} – {self.name}"
