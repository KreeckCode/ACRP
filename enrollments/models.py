from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import os
import uuid

User = get_user_model()


def get_document_upload_path(instance, filename):
    """
    Generate dynamic upload path for documents.
    
    Path structure: enrollments/docs/{year}/{month}/{council}/{application_type}/{unique_filename}
    This provides better organization and prevents filename conflicts.
    """
    # Get application details for better path organization
    app_type = 'unknown'
    council_type = 'unknown'
    
    if hasattr(instance.content_object, 'get_application_type'):
        app_type = instance.content_object.get_application_type()
    
    if hasattr(instance.content_object, 'council'):
        council_type = instance.content_object.council.code.lower()
    
    # Generate unique filename to prevent conflicts
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    
    return f"enrollments/docs/{timezone.now().year}/{timezone.now().month:02d}/{council_type}/{app_type}/{unique_filename}"


# ============================================================================
# CORE REFERENCE MODELS - These define the structure of the system
# ============================================================================

class Council(models.Model):
    """
    Represents the three councils: CGMP, CPSC, CMTP.
    
    This model centralizes council information and makes it easy to
    add new councils in the future without code changes.
    """
    code = models.CharField(
        max_length=10, 
        unique=True, 
        help_text="Council code (e.g., CGMP, CPSC, CMTP)"
    )
    name = models.CharField(
        max_length=200, 
        help_text="Full council name"
    )
    description = models.TextField(
        blank=True, 
        help_text="Detailed description of council purpose"
    )
    
    # Configuration flags
    has_subcategories = models.BooleanField(
        default=False, 
        help_text="Whether this council uses designation subcategories (currently only CPSC)"
    )
    is_active = models.BooleanField(
        default=True, 
        help_text="Whether this council is currently accepting applications"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['code']
        verbose_name = "Council"
        verbose_name_plural = "Councils"
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class AffiliationType(models.Model):
    """
    Represents the three main affiliation types: Associated, Designated, Student.
    
    This normalizes the affiliation types and makes the system more flexible.
    """
    code = models.CharField(
        max_length=20, 
        unique=True, 
        choices=[
            ('associated', 'Associated Affiliation'),
            ('designated', 'Designated Affiliation'),
            ('student', 'Student Affiliation'),
        ]
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Configuration
    requires_designation_category = models.BooleanField(
        default=False, 
        help_text="Whether this affiliation type requires selecting a designation category"
    )
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['code']
        verbose_name = "Affiliation Type"
        verbose_name_plural = "Affiliation Types"
    
    def __str__(self):
        return self.name


class DesignationCategory(models.Model):
    """
    Represents the four designation categories that apply to designated affiliations.
    
    Categories: Religious Practitioner, Advanced Religious Practitioner, 
    Religious Professional, Religious Specialist
    """
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    level = models.PositiveIntegerField(
        help_text="Hierarchical level (1-4, with 4 being highest)"
    )
    
    # Configuration
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['level', 'code']
        verbose_name = "Designation Category"
        verbose_name_plural = "Designation Categories"
    
    def __str__(self):
        return f"Level {self.level}: {self.name}"


class DesignationSubcategory(models.Model):
    """
    Represents subcategories for CPSC designated affiliations.
    
    Each designation category can have multiple subcategories, but this
    is currently only used by CPSC council.
    """
    category = models.ForeignKey(
        DesignationCategory, 
        on_delete=models.CASCADE, 
        related_name='subcategories'
    )
    council = models.ForeignKey(
        Council, 
        on_delete=models.CASCADE, 
        related_name='designation_subcategories',
        help_text="Which council this subcategory applies to"
    )
    
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Configuration
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['category__level', 'code']
        unique_together = ['category', 'council', 'code']
        verbose_name = "Designation Subcategory"
        verbose_name_plural = "Designation Subcategories"
    
    def __str__(self):
        return f"{self.category.name} - {self.name} ({self.council.code})"


# ============================================================================
# ONBOARDING MODELS - Track user's journey through onboarding process
# ============================================================================

class OnboardingSession(models.Model):
    """
    Tracks a user's onboarding session and their choices.
    
    This model captures the user's progression through the onboarding
    process and stores their selections before they create an application.
    """
    # Session identification
    session_id = models.UUIDField(
        default=uuid.uuid4, 
        unique=True, 
        help_text="Unique identifier for this onboarding session"
    )
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='onboarding_sessions',
        null=True, 
        blank=True 
    )
    
    # User selections during onboarding
    selected_affiliation_type = models.ForeignKey(
        AffiliationType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    selected_council = models.ForeignKey(
        Council, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    selected_designation_category = models.ForeignKey(
        DesignationCategory, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Only applicable for designated affiliations",
        related_name="ds"
    )
    selected_designation_subcategory = models.ForeignKey(
        DesignationSubcategory, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text="Only applicable for CPSC designated affiliations"
    )
    
    # Session metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When the user completed onboarding and created an application"
    )
    
    # Technical metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Status tracking
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('selecting_affiliation', 'Selecting Affiliation Type'),
        ('selecting_council', 'Selecting Council'),
        ('selecting_category', 'Selecting Designation Category'),
        ('selecting_subcategory', 'Selecting Designation Subcategory'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    status = models.CharField(
        max_length=30, 
        choices=STATUS_CHOICES, 
        default='started'
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Onboarding Session"
        verbose_name_plural = "Onboarding Sessions"
    
    def clean(self):
        """Validate onboarding choices consistency"""
        errors = {}
        
        # If designation category is selected, affiliation type must be 'designated'
        if self.selected_designation_category:
            if not self.selected_affiliation_type or self.selected_affiliation_type.code != 'designated':
                errors['selected_designation_category'] = _(
                    "Designation category can only be selected for designated affiliations"
                )
        
        # If subcategory is selected, must have category and council that supports subcategories
        if self.selected_designation_subcategory:
            if not self.selected_designation_category:
                errors['selected_designation_subcategory'] = _(
                    "Must select designation category before subcategory"
                )
            if not self.selected_council or not self.selected_council.has_subcategories:
                errors['selected_designation_subcategory'] = _(
                    "Selected council does not support subcategories"
                )
        
        if errors:
            raise ValidationError(errors)
    
    def is_complete(self):
        """Check if onboarding session has all required selections"""
        if not all([self.selected_affiliation_type, self.selected_council]):
            return False
        
        # If designated affiliation, must have category
        if self.selected_affiliation_type.code == 'designated':
            if not self.selected_designation_category:
                return False
            
            # If council has subcategories (CPSC), must select subcategory
            if self.selected_council.has_subcategories and not self.selected_designation_subcategory:
                return False
        
        return True
    
    def get_application_class(self):
        """Return the appropriate application class for this onboarding session"""
        if not self.is_complete():
            return None
        
        affiliation_code = self.selected_affiliation_type.code
        if affiliation_code == 'associated':
            return AssociatedApplication
        elif affiliation_code == 'designated':
            return DesignatedApplication
        elif affiliation_code == 'student':
            return StudentApplication
        
        return None
    
    def __str__(self):
        return f"Onboarding: {self.user.username} - {self.status}"


# ============================================================================
# APPLICATION MODELS - The actual application forms
# ============================================================================
# In your models.py - Replace the existing BaseApplication class with this:

class BaseApplication(models.Model):
    """
    Abstract base model for all application types.
    
    Contains common fields shared across all application forms while
    allowing specific application types to add their unique fields.
    """
    # Link to onboarding session
    onboarding_session = models.OneToOneField(
        OnboardingSession, 
        on_delete=models.CASCADE,
        related_name='%(class)s_application' 
    )
    
    # Application metadata
    application_number = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True,
        help_text="Auto-generated application reference number"
    )
    
    # Approval workflow
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('requires_clarification', 'Requires Clarification'),
    ]
    status = models.CharField(
        max_length=30, 
        choices=STATUS_CHOICES, 
        default='draft'
    )
    
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    # Staff assignments
    submitted_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='%(class)s_submissions'
    )
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='%(class)s_reviews'
    )
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='%(class)s_approvals'
    )
    
    # Review notes
    reviewer_notes = models.TextField(
        blank=True,
        help_text="Internal notes from reviewers"
    )
    rejection_reason = models.TextField(
        blank=True,
        help_text="Reason for rejection (visible to applicant)"
    )
    
    # ========================================================================
    # PERSONAL INFORMATION - Common to all application types
    # ========================================================================
    
    TITLE_CHOICES = [
        ('Mr', 'Mr'), ('Mrs', 'Mrs'), ('Miss', 'Miss'), 
        ('Dr', 'Dr'), ('Prof', 'Prof'), ('Rev', 'Rev'),
        ('Pastor', 'Pastor'), ('Bishop', 'Bishop'), ('Apostle', 'Apostle'),
        ('Elder', 'Elder'), ('Deacon', 'Deacon'), ('Minister', 'Minister')
    ]
    GENDER_CHOICES = [('male', 'Male'), ('female', 'Female')]
    RACE_CHOICES = [
        ('african', 'African'), 
        ('coloured', 'Coloured'), 
        ('indian', 'Indian'), 
        ('white', 'White'),
        ('asian', 'Asian'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say')
    ]
    
    title = models.CharField(max_length=20, choices=TITLE_CHOICES)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES)
    surname = models.CharField(max_length=150, help_text="Last name")
    initials = models.CharField(max_length=10)
    full_names = models.CharField(
        max_length=300, 
        help_text="All first names and middle names"
    )
    preferred_name = models.CharField(max_length=50, blank=True)
    
    # Identity documents
    id_number = models.CharField(
        max_length=20, 
        unique=True,
        help_text="South African ID number (13 digits)"
    )
    passport_number = models.CharField(
        max_length=30, 
        blank=True,
        help_text="For non-SA citizens or dual nationality"
    )
    
    # Demographics
    date_of_birth = models.DateField()
    race = models.CharField(max_length=30, choices=RACE_CHOICES)
    
    # SAQA Disability codes - properly structured for compliance
    DISABILITY_CHOICES = [
        ('N', 'None'),
        ('01', 'Sight (even with glasses)'),
        ('02', 'Hearing (even with hearing aid)'),
        ('03', 'Communication (talk/listen)'),
        ('04', 'Physical (move/stand etc)'),
        ('05', 'Intellectual (learn etc)'),
        ('06', 'Emotional (behaviour/psych)'),
        ('07', 'Multiple'),
        ('09', 'Disabled but unspecified'),
    ]
    
    disability = models.CharField(
        max_length=2,
        choices=DISABILITY_CHOICES,
        default='N',
        blank=True,
        help_text="SAQA requirement - Specify if you have any disabilities"
    )
    
    # Country codes using 2-character ISO codes for database efficiency
    RESIDENCY_CHOICES = [
        ('SA', 'South Africa'),
        ('AO', 'Angola'),
        ('BW', 'Botswana'),
        ('LS', 'Lesotho'),
        ('MW', 'Malawi'),
        ('MU', 'Mauritius'),
        ('MZ', 'Mozambique'),
        ('NA', 'Namibia'),
        ('SC', 'Seychelles'),
        ('SZ', 'Eswatini (Swaziland)'),
        ('TZ', 'Tanzania'),
        ('CD', 'Democratic Republic of Congo'),
        ('ZM', 'Zambia'),
        ('ZW', 'Zimbabwe'),
        ('AS', 'Asian countries'),
        ('AU', 'Australia & Oceania'),
        ('EU', 'European countries'),
        ('US', 'North American countries'),
        ('BR', 'South & Central American countries'),
        ('AF', 'Rest of Africa'),
        ('OC', 'Other & Rest of Oceania'),
        ('U', 'Unspecified'),
    ]
    
    residency = models.CharField(
        max_length=2,
        choices=RESIDENCY_CHOICES,
        default='SA',
        help_text="Country of residence * SAQA Requirement"
    )
    
    NATIONALITY_CHOICES = [
        ('SA', 'South Africa'),
        ('AO', 'Angola'),
        ('BW', 'Botswana'),
        ('LS', 'Lesotho'),
        ('MW', 'Malawi'),
        ('MU', 'Mauritius'),
        ('MZ', 'Mozambique'),
        ('NA', 'Namibia'),
        ('SC', 'Seychelles'),
        ('SZ', 'Eswatini (Swaziland)'),
        ('TZ', 'Tanzania'),
        ('CD', 'Democratic Republic of Congo'),
        ('ZM', 'Zambia'),
        ('ZW', 'Zimbabwe'),
        ('AS', 'Asian countries'),
        ('AU', 'Australia & Oceania'),
        ('EU', 'European countries'),
        ('US', 'North American countries'),
        ('BR', 'South & Central American countries'),
        ('AF', 'Rest of Africa'),
        ('OC', 'Other & Rest of Oceania'),
        ('U', 'Unspecified'),
    ]
    
    nationality = models.CharField(
        max_length=2,
        choices=NATIONALITY_CHOICES,
        default='SA', 
        help_text="Country of citizenship * SAQA Requirement"
    )
    
    # ========================================================================
    # CONTACT INFORMATION
    # ========================================================================
    
    email = models.EmailField(help_text="Primary email address")
    cell_phone = models.CharField(max_length=20, help_text="Mobile number")
    work_phone = models.CharField(max_length=20, blank=True)
    home_phone = models.CharField(max_length=20, blank=True)
    fax = models.CharField(max_length=20, blank=True)
    
    # Postal address
    postal_address_line1 = models.CharField(max_length=100)
    postal_address_line2 = models.CharField(max_length=100, blank=True)
    postal_city = models.CharField(max_length=50)
    postal_province = models.CharField(max_length=50)
    postal_code = models.CharField(max_length=10)
    postal_country = models.CharField(max_length=50, default='South Africa')
    
    # Physical address (if different from postal)
    physical_same_as_postal = models.BooleanField(
        default=True,
        help_text="Check if physical address is the same as postal address"
    )
    physical_address_line1 = models.CharField(max_length=100, blank=True)
    physical_address_line2 = models.CharField(max_length=100, blank=True)
    physical_city = models.CharField(max_length=50, blank=True)
    physical_province = models.CharField(max_length=50, blank=True)
    physical_code = models.CharField(max_length=10, blank=True)
    physical_country = models.CharField(max_length=50, blank=True)
    
    # ========================================================================
    # RELIGIOUS AND LINGUISTIC INFORMATION
    # ========================================================================
    
    religious_affiliation = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Optional: Your religious denomination or affiliation"
    )
    home_language = models.CharField(
        max_length=50,
        help_text="Your first/primary language"
    )
    other_languages = models.CharField(
        max_length=200, 
        blank=True,
        help_text="Other languages you speak (comma-separated)"
    )
    
    # ========================================================================
    # EDUCATIONAL BACKGROUND
    # ========================================================================
    
    highest_qualification = models.CharField(
        max_length=200,
        help_text="Your highest educational qualification"
    )
    qualification_institution = models.CharField(
        max_length=200,
        help_text="Institution where you obtained your highest qualification"
    )
    qualification_date = models.DateField(
        help_text="Date when qualification was awarded"
    )
    
    # ========================================================================
    # PROFESSIONAL BACKGROUND
    # ========================================================================
    
    current_occupation = models.CharField(
        max_length=100,
        help_text="Your current job title or occupation"
    )
    work_description = models.TextField(
        help_text="Detailed description of your current work responsibilities"
    )
    years_in_ministry = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(70)],
        help_text="Total years involved in ministry work"
    )
    
    # ========================================================================
    # BACKGROUND CHECKS
    # ========================================================================
    
    disciplinary_action = models.BooleanField(
        default=False,
        help_text="Have you ever been subject to disciplinary action by any professional body?"
    )
    disciplinary_description = models.TextField(
        blank=True,
        help_text="If yes, please provide details of the disciplinary action"
    )
    
    # ========================================================================
    # PASTORAL COUNSELLING INVOLVEMENT (Common question)
    # ========================================================================
    
    actively_involved_pastoral_counselling = models.BooleanField(
        default=False,
        help_text="Are you actively involved in pastoral counselling?"
    )
    
    # ========================================================================
    # LEGAL AGREEMENTS
    # ========================================================================
    
    popi_act_accepted = models.BooleanField(
        default=False,
        help_text="I consent to the processing of my personal information in terms of POPIA"
    )
    terms_accepted = models.BooleanField(
        default=False,
        help_text="I agree to the terms and conditions"
    )
    information_accurate = models.BooleanField(
        default=False,
        help_text="I certify that all information provided is true and accurate"
    )
    declaration_accepted = models.BooleanField(
        default=False,
        help_text="I understand and accept the professional obligations"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Generic relation to documents
    documents = GenericRelation('Document')
    references = GenericRelation('Reference')
    
    class Meta:
        abstract = True
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        """Override save to generate application number and normalize data"""
        # Generate application number if not set
        if not self.application_number:
            self.application_number = self.generate_application_number()
        
        # Normalize data
        if self.email:
            self.email = self.email.lower().strip()
        if self.id_number:
            self.id_number = self.id_number.replace(' ', '').replace('-', '')
        
        # Set submitted timestamp when status changes to submitted
        if self.status == 'submitted' and not self.submitted_at:
            self.submitted_at = timezone.now()
            self.submitted_by = getattr(self, '_submitted_by', None)
        
        # Call full_clean to trigger validation
        self.full_clean()
        super().save(*args, **kwargs)
    
    def clean(self):
        """Custom validation logic"""
        super().clean()
        errors = {}
        
        # Validate ID number format
        if self.id_number:
            id_clean = self.id_number.replace(' ', '').replace('-', '')
            if not id_clean.isdigit() or len(id_clean) != 13:
                errors['id_number'] = _("ID number must be exactly 13 digits")
        
        # Validate age
        if self.date_of_birth:
            today = timezone.now().date()
            age = today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
            if self.date_of_birth > today:
                errors['date_of_birth'] = _("Date of birth cannot be in the future")
            elif age < 16:
                errors['date_of_birth'] = _("Applicant must be at least 16 years old")
            elif age > 100:
                errors['date_of_birth'] = _("Please verify the date of birth")
        
        # Validate disciplinary action details
        if self.disciplinary_action and not self.disciplinary_description.strip():
            errors['disciplinary_description'] = _(
                "Details required when disciplinary action is indicated"
            )
        
        # Validate legal agreements
        required_agreements = [
            ('popi_act_accepted', 'POPIA consent'),
            ('terms_accepted', 'Terms and conditions'),
            ('information_accurate', 'Information accuracy certification'),
            ('declaration_accepted', 'Professional declaration')
        ]
        
        for field, description in required_agreements:
            if not getattr(self, field):
                errors[field] = _(f"You must accept {description} to continue")
        
        # Validate physical address if different from postal
        if not self.physical_same_as_postal:
            required_physical_fields = [
                'physical_address_line1', 'physical_city', 
                'physical_province', 'physical_code'
            ]
            for field in required_physical_fields:
                if not getattr(self, field):
                    errors[field] = _(
                        "This field is required when physical address differs from postal"
                    )
        
        if errors:
            raise ValidationError(errors)
    
    def generate_application_number(self):
        """Generate unique application number"""
        # Format: {COUNCIL_CODE}{AFFILIATION_CODE}{YEAR}{SEQUENCE}
        # Example: CGMPAS240001, CPSCDE240002, CMTPST240003
        council_code = self.get_council().code
        affiliation_code = self.get_affiliation_type()[:2].upper()
        year = timezone.now().year % 100  # Last 2 digits of year
        
        # Get next sequence number
        sequence = self.__class__.objects.filter(
            onboarding_session__selected_council=self.get_council(),
            onboarding_session__selected_affiliation_type__code=self.get_affiliation_type(),
            created_at__year=timezone.now().year
        ).count() + 1
        
        return f"{council_code}{affiliation_code}{year:02d}{sequence:04d}"
    
    def get_council(self):
        """Get the council from onboarding session"""
        return self.onboarding_session.selected_council
    
    def get_affiliation_type(self):
        """Get the affiliation type code from onboarding session"""
        return self.onboarding_session.selected_affiliation_type.code
    
    def get_application_type(self):
        """Return application type for path generation"""
        return self.get_affiliation_type()
    
    def get_full_name(self):
        """Return complete name"""
        return f"{self.full_names} {self.surname}".strip()
    
    def get_display_name(self):
        """Return preferred name or full name"""
        return self.preferred_name if self.preferred_name else self.get_full_name()
    
    def get_ministry_experience_display(self):
        """Return formatted ministry experience"""
        if self.years_in_ministry == 0:
            return "No ministry experience"
        elif self.years_in_ministry == 1:
            return "1 year"
        else:
            return f"{self.years_in_ministry} years"
    
    def can_be_submitted(self):
        """Check if application is ready for submission"""
        # Must have all required legal agreements
        if not all([
            self.popi_act_accepted, 
            self.terms_accepted, 
            self.information_accurate,
            self.declaration_accepted
        ]):
            return False
        
        # Must be in draft status
        return self.status == 'draft'
    
    def submit(self, submitted_by=None):
        """Submit the application"""
        if not self.can_be_submitted():
            raise ValidationError("Application cannot be submitted in current state")
        
        self.status = 'submitted'
        self.submitted_at = timezone.now()
        self.submitted_by = submitted_by
        self.save()



        
class AssociatedApplication(BaseApplication):
    """
    Associated Affiliation Application.
    
    This is the standard membership application with basic requirements.
    Used by all three councils (CGMP, CPSC, CMTP).
    """
    
    # No additional fields beyond BaseApplication
    # The associated application uses only the common fields
    
    class Meta:
        verbose_name = "Associated Affiliation Application"
        verbose_name_plural = "Associated Affiliation Applications"
    
    def __str__(self):
        return f"Associated: {self.get_display_name()} ({self.get_council().code})"


class StudentApplication(BaseApplication):
    """
    Student Affiliation Application.
    
    Similar to Associated but for students/trainees.
    Used by all three councils (CGMP, CPSC, CMTP).
    """
    
    # Student-specific fields
    current_institution = models.CharField(
        max_length=200,
        help_text="Name of current educational institution"
    )
    course_of_study = models.CharField(
        max_length=200,
        help_text="Current course or program of study"
    )
    expected_graduation = models.DateField(
        help_text="Expected graduation/completion date"
    )
    
    # Academic details
    student_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Student number at current institution"
    )
    year_of_study = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Current year of study"
    )
    
    # Supervision details
    academic_supervisor_name = models.CharField(max_length=200)
    academic_supervisor_email = models.EmailField()
    academic_supervisor_phone = models.CharField(max_length=20)
    
    class Meta:
        verbose_name = "Student Affiliation Application"
        verbose_name_plural = "Student Affiliation Applications"
    
    def clean(self):
        """Student-specific validation"""
        super().clean()
        errors = {}
        
        # Expected graduation should be in the future
        if self.expected_graduation and self.expected_graduation <= timezone.now().date():
            errors['expected_graduation'] = _("Expected graduation should be in the future")
        
        if errors:
            raise ValidationError(errors)
    
    def __str__(self):
        return f"Student: {self.get_display_name()} ({self.get_council().code})"


class DesignatedApplication(BaseApplication):
    # Designation level (from onboarding)
    designation_category = models.ForeignKey(
        DesignationCategory, 
        on_delete=models.PROTECT,
        help_text="Level of designation being applied for"
    )
    designation_subcategory = models.ForeignKey(
        DesignationSubcategory, 
        on_delete=models.PROTECT,
        null=True, 
        blank=True,
        help_text="Subcategory (only for CPSC applications)"
    )
    
    # ========================================================================
    # COMPREHENSIVE ACADEMIC RECORD
    # ========================================================================
    
    # High School
    high_school_name = models.CharField(max_length=200, blank=True)
    high_school_year_completed = models.PositiveIntegerField(null=True, blank=True)
    
    # Tertiary Education - we'll handle multiple qualifications via related model
    
    # ========================================================================
    # SUPERVISION RECORD
    # ========================================================================
    
    supervisor_name = models.CharField(
        max_length=200,
        help_text="Name and title of supervisor"
    )
    supervisor_qualification = models.CharField(
        max_length=200,
        help_text="Supervisor's relevant qualifications"
    )
    supervisor_email = models.EmailField()
    supervisor_phone = models.CharField(max_length=20)
    supervisor_address = models.TextField()
    
    supervision_hours_received = models.PositiveIntegerField(
        default=0,
        help_text="Total number of supervision hours received"
    )
    supervision_period_start = models.DateField(
        null=True, 
        blank=True,
        help_text="Start date of supervision period"
    )
    supervision_period_end = models.DateField(
        null=True, 
        blank=True,
        help_text="End date of supervision period (if completed)"
    )
    
    # ========================================================================
    # PROFESSIONAL DEVELOPMENT
    # ========================================================================
    
    professional_development_plans = models.TextField(
        help_text="What are your plans for further development of your professional knowledge and skills?"
    )
    
    # ========================================================================
    # PROFESSIONAL BOARDS AND ORGANISATIONS
    # ========================================================================
    
    other_professional_memberships = models.TextField(
        blank=True,
        help_text="List other professional bodies you are affiliated with"
    )
    
    class Meta:
        verbose_name = "Designated Affiliation Application"
        verbose_name_plural = "Designated Affiliation Applications"
    
    def clean(self):
        """Designated application specific validation"""
        super().clean()
        errors = {}
        
        # If council has subcategories (CPSC), subcategory is required
        council = self.get_council()
        if council.has_subcategories and not self.designation_subcategory:
            errors['designation_subcategory'] = _(
                "Subcategory selection is required for this council"
            )
        
        # If subcategory is selected, it must match the category and council
        if self.designation_subcategory:
            if self.designation_subcategory.category != self.designation_category:
                errors['designation_subcategory'] = _(
                    "Subcategory must belong to the selected category"
                )
            if self.designation_subcategory.council != council:
                errors['designation_subcategory'] = _(
                    "Subcategory must belong to the selected council"
                )
        
        # Validate supervision period
        if self.supervision_period_start and self.supervision_period_end:
            if self.supervision_period_end <= self.supervision_period_start:
                errors['supervision_period_end'] = _(
                    "End date must be after start date"
                )
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to set designation fields from onboarding session"""
        if not self.designation_category and self.onboarding_session.selected_designation_category:
            self.designation_category = self.onboarding_session.selected_designation_category
        
        if not self.designation_subcategory and self.onboarding_session.selected_designation_subcategory:
            self.designation_subcategory = self.onboarding_session.selected_designation_subcategory
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        category_name = self.designation_category.name if self.designation_category else "Unknown"
        subcategory_display = ""
        if self.designation_subcategory:
            subcategory_display = f" - {self.designation_subcategory.name}"
        
        return f"Designated: {self.get_display_name()} ({category_name}{subcategory_display})"


# ============================================================================
# RELATED MODELS - Supporting models for applications
# ============================================================================

class AcademicQualification(models.Model):
    """
    Academic qualifications for designated applications.
    
    Supports multiple qualifications per application including
    high school, college, seminary, university, and other qualifications.
    """
    application = models.ForeignKey(
        DesignatedApplication, 
        on_delete=models.CASCADE,
        related_name='academic_qualifications'
    )
    
    QUALIFICATION_TYPES = [
        ('high_school', 'High School'),
        ('college', 'College'),
        ('seminary', 'Seminary'),
        ('university', 'University'),
        ('other', 'Other'),
    ]
    
    qualification_type = models.CharField(
        max_length=20, 
        choices=QUALIFICATION_TYPES
    )
    qualification_name = models.CharField(
        max_length=200,
        help_text="e.g., BSc Theology, Diploma in Pastoral Care"
    )
    institution_name = models.CharField(max_length=200)
    institution_address = models.TextField(blank=True)
    date_awarded = models.DateField()
    
    # Additional details
    grade_or_class = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Grade achieved or class of degree"
    )
    
    class Meta:
        ordering = ['-date_awarded']
        verbose_name = "Academic Qualification"
        verbose_name_plural = "Academic Qualifications"
    
    def __str__(self):
        return f"{self.qualification_name} - {self.institution_name} ({self.date_awarded.year})"


class Reference(models.Model):
    """
    Reference/referral letters for applications.
    
    Designated applications require 2 references with letters.
    Other applications may have references without mandatory letters.
    """
    # Polymorphic relationship to any application type
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Reference details
    reference_title = models.CharField(
        max_length=20, 
        choices=BaseApplication.TITLE_CHOICES
    )
    reference_surname = models.CharField(max_length=150)
    reference_names = models.CharField(max_length=300)
    reference_email = models.EmailField()
    reference_phone = models.CharField(max_length=20)
    reference_address = models.TextField()
    
    nature_of_relationship = models.CharField(
        max_length=200,
        help_text="How you know this person (e.g., supervisor, colleague, pastor)"
    )
    
    # Reference letter (required for designated applications)
    letter_required = models.BooleanField(
        default=False,
        help_text="Whether a formal reference letter is required"
    )
    letter_received = models.BooleanField(default=False)
    letter_received_date = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Generic relation to documents (for uploaded reference letters)
    documents = GenericRelation('Document')
    
    class Meta:
        ordering = ['reference_surname', 'reference_names']
        verbose_name = "Reference"
        verbose_name_plural = "References"
    
    def get_reference_full_name(self):
        """Return referee's full name"""
        return f"{self.reference_names} {self.reference_surname}".strip()
    
    def __str__(self):
        return f"Reference: {self.get_reference_full_name()} for {self.content_object}"


class PracticalExperience(models.Model):
    """
    Record of relevant practical experience for designated applications.
    
    Tracks professional experience in relevant ministry/counselling contexts.
    """
    application = models.ForeignKey(
        DesignatedApplication,
        on_delete=models.CASCADE,
        related_name='practical_experiences'
    )
    
    institution_name = models.CharField(
        max_length=200,
        help_text="Name of organization/institution"
    )
    contact_person_name = models.CharField(max_length=200)
    contact_person_email = models.EmailField()
    contact_person_phone = models.CharField(max_length=20)
    
    basic_nature_of_work = models.TextField(
        help_text="Describe the basic nature of work/ministry performed"
    )
    
    # Period of experience
    start_date = models.DateField()
    end_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Leave blank if currently ongoing"
    )
    
    # Additional details
    hours_per_week = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Average hours per week"
    )
    
    class Meta:
        ordering = ['-start_date']
        verbose_name = "Practical Experience"
        verbose_name_plural = "Practical Experiences"
    
    def clean(self):
        """Validate date ranges"""
        if self.end_date and self.end_date <= self.start_date:
            raise ValidationError({'end_date': _("End date must be after start date")})
    
    def get_duration_display(self):
        """Return formatted duration"""
        end = self.end_date or timezone.now().date()
        duration = end - self.start_date
        
        if duration.days < 30:
            return f"{duration.days} days"
        elif duration.days < 365:
            months = duration.days // 30
            return f"{months} month{'s' if months != 1 else ''}"
        else:
            years = duration.days // 365
            months = (duration.days % 365) // 30
            if months == 0:
                return f"{years} year{'s' if years != 1 else ''}"
            else:
                return f"{years} year{'s' if years != 1 else ''}, {months} month{'s' if months != 1 else ''}"
    
    def __str__(self):
        return f"{self.institution_name} ({self.start_date} - {self.end_date or 'Present'})"


# ============================================================================
# DOCUMENT MANAGEMENT
# ============================================================================

class Document(models.Model):
    """
    Enhanced document model with better categorization and metadata.
    
    Supports polymorphic relationships to any application type and
    provides comprehensive document management capabilities.
    """
    DOCUMENT_CATEGORIES = [
        # General documents
        ('id_document', 'ID Document'),
        ('passport', 'Passport'),
        ('proof_of_payment', 'Proof of Payment'),
        
        # Academic documents
        ('qualification_certificate', 'Qualification Certificate'),
        ('academic_transcript', 'Academic Transcript'),
        ('diploma', 'Diploma'),
        ('degree_certificate', 'Degree Certificate'),
        
        # Professional documents
        ('ordination_certificate', 'Ordination Certificate'),
        ('professional_certification', 'Professional Certification'),
        ('professional_registration', 'Professional Registration'),
        ('insurance_certificate', 'Insurance Certificate'),
        ('cv', 'Curriculum Vitae'),
        
        # Reference documents
        ('reference_letter', 'Reference Letter'),
        ('recommendation_letter', 'Letter of Recommendation'),
        
        # Ministry documents
        ('ministry_experience_letter', 'Ministry Experience Letter'),
        ('supervision_record', 'Supervision Record'),
        
        # Other
        ('supporting_document', 'Supporting Document'),
        ('other', 'Other'),
    ]

    # Polymorphic relationship
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Document details
    category = models.CharField(max_length=30, choices=DOCUMENT_CATEGORIES)
    title = models.CharField(
        max_length=200,
        help_text="Descriptive title for this document"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of document contents"
    )
    
    # File details
    file = models.FileField(
        upload_to=get_document_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'gif']
            )
        ]
    )
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    
    # Upload metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='uploaded_documents'
    )
    
    # Verification workflow
    is_required = models.BooleanField(
        default=False,
        help_text="Whether this document is required for the application"
    )
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(
        blank=True,
        help_text="Notes from document verification"
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Document"
        verbose_name_plural = "Documents"
    
    def clean(self):
        """Validate file size and type"""
        if self.file:
            # Check file size (10MB limit)
            if self.file.size > 10 * 1024 * 1024:
                raise ValidationError({'file': _("File size cannot exceed 10MB")})
    
    def save(self, *args, **kwargs):
        """Override save to capture file metadata"""
        if self.file:
            self.original_filename = self.file.name
            self.file_size = self.file.size
            
            # Set mime type based on extension
            ext = os.path.splitext(self.file.name)[1].lower()
            mime_types = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
            }
            self.mime_type = mime_types.get(ext, 'application/octet-stream')
        
        super().save(*args, **kwargs)
    
    def get_file_extension(self):
        """Return file extension"""
        return os.path.splitext(self.original_filename)[1].lower()
    
    def get_file_size_display(self):
        """Return human-readable file size"""
        if self.file_size < 1024:
            return f"{self.file_size} bytes"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
    
    def verify(self, verified_by=None, notes=''):
        """Mark document as verified"""
        self.verified = True
        self.verified_by = verified_by
        self.verified_at = timezone.now()
        self.verification_notes = notes
        self.save()
    
    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"