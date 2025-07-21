from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.timezone import now
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import uuid
from datetime import datetime, timedelta


User = get_user_model()


# ============================================================================
# FOUNDATIONAL MODELS - System Configuration
# ============================================================================

class CPDProvider(models.Model):
    """
    Organizations or institutions that provide CPD activities.
    Can be internal (ACRP) or external providers.
    """
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Provider classification
    class ProviderType(models.TextChoices):
        INTERNAL = 'INTERNAL', _('ACRP Internal')
        ACCREDITED = 'ACCREDITED', _('Accredited External')
        EXTERNAL = 'EXTERNAL', _('External Provider')
        UNIVERSITY = 'UNIVERSITY', _('University/Institution')
        PROFESSIONAL_BODY = 'PROFESSIONAL_BODY', _('Professional Body')
    
    provider_type = models.CharField(
        max_length=20,
        choices=ProviderType.choices,
        default=ProviderType.EXTERNAL
    )
    
    # Quality and trust indicators
    is_accredited = models.BooleanField(
        default=False,
        help_text="Whether this provider is officially accredited"
    )
    accreditation_body = models.CharField(max_length=200, blank=True)
    quality_rating = models.DecimalField(
        max_digits=3, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        null=True, blank=True,
        help_text="Quality rating out of 5"
    )
    
    # Administrative fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_providers'
    )

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['provider_type', 'is_active']),
            models.Index(fields=['is_accredited']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"

    def get_absolute_url(self):
        return reverse('cpd:provider_detail', kwargs={'pk': self.pk})


class CPDCategory(models.Model):
    """
    Categories of CPD activities (e.g., Formal Learning, Self-Study, Conferences).
    Defines point values and requirements for different types of learning.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    short_code = models.CharField(
        max_length=10, unique=True,
        help_text="Short code for category (e.g., FL, SS, CNF)"
    )
    
    # Point calculation settings
    points_per_hour = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=1.00,
        help_text="Default points awarded per hour for this category"
    )
    
    # Category constraints
    min_hours_per_activity = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=0.50,
        help_text="Minimum hours required for an activity in this category"
    )
    max_hours_per_activity = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=40.00,
        help_text="Maximum hours allowed for a single activity"
    )
    
    # Evidence requirements
    requires_evidence = models.BooleanField(
        default=True,
        help_text="Whether activities in this category require supporting evidence"
    )
    evidence_description = models.TextField(
        blank=True,
        help_text="Description of what evidence is required"
    )
    
    # Approval workflow
    requires_approval = models.BooleanField(
        default=True,
        help_text="Whether activities in this category require admin approval"
    )
    auto_approve_threshold = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Auto-approve activities under this hour threshold"
    )
    
    # Quality multipliers
    accredited_multiplier = models.DecimalField(
        max_digits=3, decimal_places=2,
        default=1.00,
        help_text="Point multiplier for accredited providers (e.g., 1.2 = 20% bonus)"
    )
    
    # Administrative fields
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "CPD Category"
        verbose_name_plural = "CPD Categories"

    def __str__(self):
        return f"{self.name} ({self.short_code})"

    def calculate_points(self, hours, provider=None):
        """Calculate points for given hours in this category."""
        base_points = hours * self.points_per_hour
        
        # Apply accredited provider bonus
        if provider and provider.is_accredited:
            base_points *= self.accredited_multiplier
            
        return round(base_points, 2)


class CPDRequirement(models.Model):
    """
    CPD requirements for different councils and user levels.
    Defines annual point requirements and category-specific minimums.
    """
    # Council affiliation
    class Council(models.TextChoices):
        CGMP = 'CGMP', _('Council for General Ministry Professionals')
        CPSC = 'CPSC', _('Council for Pastoral & Spiritual Care')
        CMTP = 'CMTP', _('Council for Ministry Training Providers')
        ALL = 'ALL', _('All Councils')
    
    council = models.CharField(
        max_length=10,
        choices=Council.choices,
        default=Council.ALL
    )
    
    # User level/classification
    class UserLevel(models.TextChoices):
        LEARNER = 'LEARNER', _('Learner')
        ASSOCIATE = 'ASSOCIATE', _('Associate Member')
        FULL_MEMBER = 'FULL_MEMBER', _('Full Member')
        FACILITATOR = 'FACILITATOR', _('Facilitator')
        ASSESSOR = 'ASSESSOR', _('Assessor')
        ALL_LEVELS = 'ALL_LEVELS', _('All Levels')
    
    user_level = models.CharField(
        max_length=15,
        choices=UserLevel.choices,
        default=UserLevel.ALL_LEVELS
    )
    
    # Requirement details
    name = models.CharField(max_length=200)
    description = models.TextField()
    
    # Annual requirements
    total_points_required = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Total CPD points required annually"
    )
    total_hours_required = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Total CPD hours required annually"
    )
    
    # Category-specific requirements
    category_requirements = models.JSONField(
        default=dict,
        help_text="Category-specific minimums: {'category_id': {'min_points': X, 'min_hours': Y}}"
    )
    
    # Flexibility settings
    carry_over_allowed = models.BooleanField(
        default=False,
        help_text="Allow carrying over excess points from previous year"
    )
    carry_over_max_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=0.00,
        help_text="Maximum percentage of points that can be carried over"
    )
    
    # Timing and validity
    effective_date = models.DateField(help_text="When this requirement becomes effective")
    expiry_date = models.DateField(
        null=True, blank=True,
        help_text="When this requirement expires (null = indefinite)"
    )
    
    # Administrative fields
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_requirements'
    )

    class Meta:
        ordering = ['council', 'user_level', '-effective_date']
        unique_together = ['council', 'user_level', 'effective_date']
        indexes = [
            models.Index(fields=['council', 'user_level']),
            models.Index(fields=['effective_date', 'expiry_date']),
        ]

    def __str__(self):
        return f"{self.get_council_display()} - {self.get_user_level_display()} ({self.total_points_required} pts)"

    def is_valid_for_date(self, date):
        """Check if this requirement is valid for a given date."""
        if date < self.effective_date:
            return False
        if self.expiry_date and date > self.expiry_date:
            return False
        return True

    def get_category_requirement(self, category):
        """Get specific requirements for a category."""
        return self.category_requirements.get(str(category.id), {})


# ============================================================================
# ACTIVITY MODELS - CPD Activities and Events
# ============================================================================

class CPDActivity(models.Model):
    """
    Specific CPD activities that users can participate in.
    Can be pre-approved or submitted for approval.
    """
    # Basic information
    title = models.CharField(max_length=300)
    description = models.TextField()
    provider = models.ForeignKey(
        CPDProvider, on_delete=models.CASCADE,
        related_name='activities'
    )
    category = models.ForeignKey(
        CPDCategory, on_delete=models.CASCADE,
        related_name='activities'
    )
    
    # Activity classification
    class ActivityType(models.TextChoices):
        COURSE = 'COURSE', _('Course/Training')
        WORKSHOP = 'WORKSHOP', _('Workshop')
        SEMINAR = 'SEMINAR', _('Seminar')
        CONFERENCE = 'CONFERENCE', _('Conference')
        WEBINAR = 'WEBINAR', _('Webinar')
        SELF_STUDY = 'SELF_STUDY', _('Self-Study')
        RESEARCH = 'RESEARCH', _('Research')
        MENTORING = 'MENTORING', _('Mentoring')
        OTHER = 'OTHER', _('Other')
    
    activity_type = models.CharField(
        max_length=15,
        choices=ActivityType.choices,
        default=ActivityType.COURSE
    )
    
    # Timing and logistics
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    duration_hours = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Duration in hours"
    )
    location = models.CharField(max_length=200, blank=True)
    is_online = models.BooleanField(default=False)
    meeting_url = models.URLField(blank=True, null=True)
    
    # Registration and capacity
    registration_required = models.BooleanField(default=False)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    registration_fee = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Registration fee (if applicable)"
    )
    
    # Pre-approval status
    class ApprovalStatus(models.TextChoices):
        PRE_APPROVED = 'PRE_APPROVED', _('Pre-Approved')
        REQUIRES_APPROVAL = 'REQUIRES_APPROVAL', _('Requires Approval')
        TEMPLATE = 'TEMPLATE', _('Template Activity')
    
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.REQUIRES_APPROVAL
    )
    
    # Point calculation
    points_awarded = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Fixed points (overrides category calculation if set)"
    )
    
    # Content and resources
    learning_objectives = models.TextField(blank=True)
    prerequisites = models.TextField(blank=True)
    materials_provided = models.TextField(blank=True)
    website_url = models.URLField(blank=True, null=True)
    
    # Quality indicators
    is_accredited = models.BooleanField(default=False)
    accreditation_body = models.CharField(max_length=200, blank=True)
    average_rating = models.DecimalField(
        max_digits=3, decimal_places=2,
        null=True, blank=True,
        help_text="Average participant rating"
    )
    total_ratings = models.PositiveIntegerField(default=0)
    
    # Administrative fields
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_activities'
    )

    class Meta:
        ordering = ['-start_date', 'title']
        verbose_name = "CPD Activity"
        verbose_name_plural = "CPD Activities"
        indexes = [
            models.Index(fields=['category', 'approval_status']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['provider', 'is_active']),
        ]

    def __str__(self):
        return f"{self.title} ({self.provider.name})"

    def get_absolute_url(self):
        return reverse('cpd:activity_detail', kwargs={'pk': self.pk})

    def clean(self):
        """Validate activity data."""
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValidationError("Start date cannot be after end date")
        
        if self.registration_required and not self.registration_deadline:
            raise ValidationError("Registration deadline is required when registration is required")

    def calculate_points(self):
        """Calculate points for this activity."""
        if self.points_awarded:
            return self.points_awarded
        return self.category.calculate_points(self.duration_hours, self.provider)

    @property
    def is_upcoming(self):
        """Check if activity is in the future."""
        if not self.start_date:
            return False
        return self.start_date > now()

    @property
    def is_registration_open(self):
        """Check if registration is still open."""
        if not self.registration_required:
            return False
        if self.registration_deadline:
            return now() <= self.registration_deadline
        return True

    @property
    def available_spots(self):
        """Get number of available registration spots."""
        if not self.max_participants:
            return None
        registered = self.records.filter(
            status__in=[CPDRecord.Status.REGISTERED, CPDRecord.Status.COMPLETED]
        ).count()
        return max(0, self.max_participants - registered)


# ============================================================================
# PARTICIPATION MODELS - User CPD Records and Evidence
# ============================================================================

class CPDPeriod(models.Model):
    """
    Annual CPD periods for tracking compliance cycles.
    """
    name = models.CharField(max_length=100, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # Period settings
    is_current = models.BooleanField(
        default=False,
        help_text="Only one period can be current at a time"
    )
    submission_deadline = models.DateField(
        help_text="Deadline for submitting CPD activities for this period"
    )
    
    # Compliance settings
    grace_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Grace period after submission deadline"
    )
    
    # Administrative fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_current']),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date.year})"

    def clean(self):
        """Validate period data."""
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")
        
        if self.submission_deadline < self.end_date:
            raise ValidationError("Submission deadline should be after period end date")

    def save(self, *args, **kwargs):
        """Ensure only one current period."""
        if self.is_current:
            CPDPeriod.objects.filter(is_current=True).update(is_current=False)
        super().save(*args, **kwargs)

    @property
    def is_submission_open(self):
        """Check if submissions are still allowed."""
        return now().date() <= self.submission_deadline

    @property
    def days_until_deadline(self):
        """Get days remaining until submission deadline."""
        delta = self.submission_deadline - now().date()
        return delta.days if delta.days > 0 else 0


class CPDRecord(models.Model):
    """
    Individual CPD activity records for users.
    Tracks participation, completion, and approval status.
    """
    # Core relationships
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='cpd_records'
    )
    activity = models.ForeignKey(
        CPDActivity, on_delete=models.CASCADE,
        related_name='records'
    )
    period = models.ForeignKey(
        CPDPeriod, on_delete=models.CASCADE,
        related_name='records'
    )
    
    # Participation details
    class Status(models.TextChoices):
        REGISTERED = 'REGISTERED', _('Registered')
        ATTENDED = 'ATTENDED', _('Attended')
        COMPLETED = 'COMPLETED', _('Completed')
        CANCELLED = 'CANCELLED', _('Cancelled')
        NO_SHOW = 'NO_SHOW', _('No Show')
        WITHDRAWN = 'WITHDRAWN', _('Withdrawn')
    
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.REGISTERED
    )
    
    # Custom activity details (for user-submitted activities)
    custom_title = models.CharField(
        max_length=300, blank=True,
        help_text="Custom title if different from activity"
    )
    custom_provider = models.CharField(
        max_length=200, blank=True,
        help_text="Custom provider if not in system"
    )
    custom_duration = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Custom duration if different from activity"
    )
    
    # Dates and completion
    registration_date = models.DateTimeField(auto_now_add=True)
    attendance_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    
    # Points and assessment
    points_claimed = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Points claimed by user"
    )
    points_awarded = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Points actually awarded after review"
    )
    hours_claimed = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Hours claimed by user"
    )
    hours_awarded = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Hours actually awarded after review"
    )
    
    # User feedback and rating
    user_rating = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="User rating of the activity (1-5)"
    )
    user_feedback = models.TextField(blank=True)
    would_recommend = models.BooleanField(null=True, blank=True)
    
    # Notes and additional information
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about participation"
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal admin notes"
    )
    
    # Administrative fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-registration_date']
        unique_together = ['user', 'activity', 'period']
        indexes = [
            models.Index(fields=['user', 'period']),
            models.Index(fields=['status', 'completion_date']),
            models.Index(fields=['activity', 'status']),
        ]

    def __str__(self):
        title = self.custom_title or self.activity.title
        return f"{self.user.get_full_name} - {title}"

    def get_absolute_url(self):
        return reverse('cpd:record_detail', kwargs={'pk': self.pk})

    @property
    def display_title(self):
        """Get the display title for this record."""
        return self.custom_title or self.activity.title

    @property
    def display_provider(self):
        """Get the display provider for this record."""
        return self.custom_provider or self.activity.provider.name

    @property
    def final_points(self):
        """Get final awarded points."""
        return self.points_awarded or self.points_claimed or 0

    @property
    def final_hours(self):
        """Get final awarded hours."""
        return self.hours_awarded or self.hours_claimed or self.activity.duration_hours

    def save(self, *args, **kwargs):
        """Auto-calculate points if not set."""
        if not self.points_claimed and self.activity:
            duration = self.custom_duration or self.activity.duration_hours
            self.points_claimed = self.activity.category.calculate_points(
                duration, self.activity.provider
            )
        super().save(*args, **kwargs)


class CPDEvidence(models.Model):
    """
    Supporting evidence/documentation for CPD activities.
    """
    record = models.ForeignKey(
        CPDRecord, on_delete=models.CASCADE,
        related_name='evidence_files'
    )
    
    # File information
    file = models.FileField(
        upload_to='cpd_evidence/%Y/%m/',
        help_text="Supporting document (PDF, DOC, JPG, PNG)"
    )
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    
    # Evidence classification
    class EvidenceType(models.TextChoices):
        CERTIFICATE = 'CERTIFICATE', _('Certificate of Completion')
        ATTENDANCE = 'ATTENDANCE', _('Attendance Record')
        TRANSCRIPT = 'TRANSCRIPT', _('Academic Transcript')
        RECEIPT = 'RECEIPT', _('Payment Receipt')
        AGENDA = 'AGENDA', _('Event Agenda/Program')
        REFLECTION = 'REFLECTION', _('Learning Reflection')
        OTHER = 'OTHER', _('Other Supporting Document')
    
    evidence_type = models.CharField(
        max_length=15,
        choices=EvidenceType.choices,
        default=EvidenceType.CERTIFICATE
    )
    
    description = models.CharField(
        max_length=200, blank=True,
        help_text="Brief description of this evidence"
    )
    
    # Verification status
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_evidence'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Administrative fields
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['record', 'evidence_type']),
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return f"{self.record.display_title} - {self.get_evidence_type_display()}"

    def save(self, *args, **kwargs):
        """Store original filename and file size."""
        if self.file:
            self.original_filename = self.file.name
            if hasattr(self.file, 'size'):
                self.file_size = self.file.size
        super().save(*args, **kwargs)


# ============================================================================
# WORKFLOW AND APPROVAL MODELS
# ============================================================================

class CPDApproval(models.Model):
    """
    Approval workflow for CPD records and activities.
    Tracks the approval process from submission to final decision.
    """
    record = models.OneToOneField(
        CPDRecord, on_delete=models.CASCADE,
        related_name='approval'
    )
    
    # Approval status
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Review')
        UNDER_REVIEW = 'UNDER_REVIEW', _('Under Review')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')
        NEEDS_MORE_INFO = 'NEEDS_MORE_INFO', _('Needs More Information')
        RESUBMITTED = 'RESUBMITTED', _('Resubmitted')
        WITHDRAWN = 'WITHDRAWN', _('Withdrawn by User')
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Review details
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cpd_reviews'
    )
    
    # Decision details
    reviewer_comments = models.TextField(
        blank=True,
        help_text="Comments from the reviewer"
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (if applicable)"
    )
    
    # Point adjustments
    original_points = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Originally claimed points"
    )
    adjusted_points = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        help_text="Adjusted points after review"
    )
    adjustment_reason = models.TextField(
        blank=True,
        help_text="Reason for point adjustment"
    )
    
    # Priority and urgency
    class Priority(models.TextChoices):
        LOW = 'LOW', _('Low')
        NORMAL = 'NORMAL', _('Normal')
        HIGH = 'HIGH', _('High')
        URGENT = 'URGENT', _('Urgent')
    
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL
    )
    
    # Workflow tracking
    days_in_review = models.PositiveIntegerField(default=0)
    auto_approved = models.BooleanField(
        default=False,
        help_text="Whether this was auto-approved by system rules"
    )
    
    # Administrative fields
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', '-submitted_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['reviewer', 'status']),
            models.Index(fields=['submitted_at', 'reviewed_at']),
        ]

    def __str__(self):
        return f"{self.record.display_title} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        """Update review timing and record points."""
        if self.status in [self.Status.APPROVED, self.Status.REJECTED] and not self.reviewed_at:
            self.reviewed_at = now()
            
        if self.reviewed_at and self.submitted_at:
            delta = self.reviewed_at - self.submitted_at
            self.days_in_review = delta.days
            
        # Update record points if approved
        if self.status == self.Status.APPROVED:
            final_points = self.adjusted_points or self.original_points
            self.record.points_awarded = final_points
            self.record.save(update_fields=['points_awarded'])
            
        super().save(*args, **kwargs)


# ============================================================================
# COMPLIANCE AND REPORTING MODELS
# ============================================================================

class CPDCompliance(models.Model):
    """
    Calculated compliance status for users in each period.
    Automatically updated when records change.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='cpd_compliance'
    )
    period = models.ForeignKey(
        CPDPeriod, on_delete=models.CASCADE,
        related_name='compliance_records'
    )
    requirement = models.ForeignKey(
        CPDRequirement, on_delete=models.CASCADE,
        related_name='compliance_records'
    )
    
    # Calculated totals
    total_points_earned = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=0
    )
    total_hours_completed = models.DecimalField(
        max_digits=8, decimal_places=2,
        default=0
    )
    
    # Category breakdowns (JSON field for flexibility)
    category_breakdown = models.JSONField(
        default=dict,
        help_text="Points and hours by category: {'category_id': {'points': X, 'hours': Y}}"
    )
    
    # Compliance status
    class Status(models.TextChoices):
        COMPLIANT = 'COMPLIANT', _('Compliant')
        NON_COMPLIANT = 'NON_COMPLIANT', _('Non-Compliant')
        AT_RISK = 'AT_RISK', _('At Risk')
        PENDING = 'PENDING', _('Pending Activities')
        EXEMPT = 'EXEMPT', _('Exempt')
    
    compliance_status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING
    )
    
    # Progress indicators
    points_progress_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=0
    )
    hours_progress_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=0
    )
    
    # Deficit tracking
    points_deficit = models.DecimalField(
        max_digits=6, decimal_places=2,
        default=0
    )
    hours_deficit = models.DecimalField(
        max_digits=6, decimal_places=2,
        default=0
    )
    
    # Important dates
    last_activity_date = models.DateField(null=True, blank=True)
    compliance_achieved_date = models.DateField(null=True, blank=True)
    
    # Administrative fields
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period__start_date', 'user__last_name']
        unique_together = ['user', 'period', 'requirement']
        indexes = [
            models.Index(fields=['compliance_status', 'period']),
            models.Index(fields=['user', 'period']),
            models.Index(fields=['points_progress_percentage']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name} - {self.period.name} ({self.get_compliance_status_display()})"

    def recalculate_compliance(self):
        """Recalculate compliance based on current records."""
        # Get approved records for this user and period
        approved_records = self.user.cpd_records.filter(
            period=self.period,
            approval__status=CPDApproval.Status.APPROVED
        )
        
        # Calculate totals
        self.total_points_earned = sum(
            record.final_points for record in approved_records
        )
        self.total_hours_completed = sum(
            record.final_hours for record in approved_records
        )
        
        # Calculate category breakdown
        breakdown = {}
        for record in approved_records:
            cat_id = str(record.activity.category.id)
            if cat_id not in breakdown:
                breakdown[cat_id] = {'points': 0, 'hours': 0}
            breakdown[cat_id]['points'] += float(record.final_points)
            breakdown[cat_id]['hours'] += float(record.final_hours)
        self.category_breakdown = breakdown
        
        # Calculate progress percentages
        if self.requirement.total_points_required > 0:
            self.points_progress_percentage = min(
                100, (self.total_points_earned / self.requirement.total_points_required) * 100
            )
        
        if self.requirement.total_hours_required > 0:
            self.hours_progress_percentage = min(
                100, (self.total_hours_completed / self.requirement.total_hours_required) * 100
            )
        
        # Calculate deficits
        self.points_deficit = max(
            0, self.requirement.total_points_required - self.total_points_earned
        )
        self.hours_deficit = max(
            0, self.requirement.total_hours_required - self.total_hours_completed
        )
        
        # Determine compliance status
        points_met = self.total_points_earned >= self.requirement.total_points_required
        hours_met = self.total_hours_completed >= self.requirement.total_hours_required
        
        if points_met and hours_met:
            self.compliance_status = self.Status.COMPLIANT
            if not self.compliance_achieved_date:
                self.compliance_achieved_date = now().date()
        elif self.points_progress_percentage >= 75 or self.hours_progress_percentage >= 75:
            self.compliance_status = self.Status.AT_RISK
        else:
            self.compliance_status = self.Status.NON_COMPLIANT
        
        # Set last activity date
        if approved_records:
            self.last_activity_date = max(
                record.completion_date or record.attendance_date 
                for record in approved_records 
                if record.completion_date or record.attendance_date
            )
        
        self.save()


class CPDCertificate(models.Model):
    """
    Generated compliance certificates for users.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='cpd_certificates'
    )
    period = models.ForeignKey(
        CPDPeriod, on_delete=models.CASCADE,
        related_name='certificates'
    )
    compliance = models.OneToOneField(
        CPDCompliance, on_delete=models.CASCADE,
        related_name='certificate'
    )
    
    # Certificate details
    certificate_number = models.CharField(max_length=50, unique=True)
    issue_date = models.DateField(auto_now_add=True)
    expiry_date = models.DateField()
    
    # Certificate content
    points_certified = models.DecimalField(max_digits=8, decimal_places=2)
    hours_certified = models.DecimalField(max_digits=8, decimal_places=2)
    
    # File storage
    certificate_file = models.FileField(
        upload_to='certificates/%Y/',
        null=True, blank=True,
        help_text="Generated PDF certificate"
    )
    
    # Verification
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_valid = models.BooleanField(default=True)
    
    # Administrative fields
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='generated_certificates'
    )

    class Meta:
        ordering = ['-issue_date']
        unique_together = ['user', 'period']
        indexes = [
            models.Index(fields=['certificate_number']),
            models.Index(fields=['verification_token']),
            models.Index(fields=['user', 'period']),
        ]

    def __str__(self):
        return f"Certificate {self.certificate_number} - {self.user.get_full_name}"

    def save(self, *args, **kwargs):
        """Generate certificate number and expiry date."""
        if not self.certificate_number:
            year = self.period.end_date.year
            user_id = str(self.user.id).zfill(4)
            self.certificate_number = f"CPD{year}{user_id}"
        
        if not self.expiry_date:
            # Certificates expire 3 years from issue
            self.expiry_date = self.issue_date + timedelta(days=365*3)
        
        super().save(*args, **kwargs)

    def get_verification_url(self):
        """Get public verification URL."""
        return reverse('cpd:verify_certificate', kwargs={'token': self.verification_token})


# ============================================================================
# AUDIT AND TRACKING MODELS
# ============================================================================

class CPDAuditLog(models.Model):
    """
    Comprehensive audit trail for all CPD-related changes.
    """
    # What was changed
    content_type = models.CharField(max_length=50)  # Model name
    object_id = models.PositiveIntegerField()
    
    # Who made the change
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='cpd_audit_logs'
    )
    
    # When and what
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(
        max_length=20,
        choices=[
            ('CREATE', 'Created'),
            ('UPDATE', 'Updated'),
            ('DELETE', 'Deleted'),
            ('APPROVE', 'Approved'),
            ('REJECT', 'Rejected'),
            ('SUBMIT', 'Submitted'),
            ('WITHDRAW', 'Withdrawn'),
        ]
    )
    
    # Change details
    field_changes = models.JSONField(
        default=dict,
        help_text="Field-level changes: {'field': {'old': 'value', 'new': 'value'}}"
    )
    
    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.action} {self.content_type}({self.object_id}) by {self.user} at {self.timestamp}"