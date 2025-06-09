from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

User = get_user_model()

# Base Abstract Model for all Affiliations
class BaseAffiliation(models.Model):
    """
    Abstract base model containing common fields for all affiliation types.
    This promotes DRY principles and ensures consistency across council types.
    """
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_user = models.ForeignKey(
        User, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='%(class)s_created_by',
        editable=False
    )
    
    # Approval workflow
    approved = models.BooleanField(default=False, editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    approved_by = models.ForeignKey(
        User, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='%(class)s_approved_by',
        editable=False
    )
    
    # Personal Information
    GENDER_CHOICES = [('male', 'Male'), ('female', 'Female'), ('other', 'Other')]
    TITLE_CHOICES = [
        ('Mr', 'Mr'), ('Mrs', 'Mrs'), ('Miss', 'Miss'), 
        ('Dr', 'Dr'), ('Prof', 'Prof'), ('Rev', 'Rev'),
        ('Pastor', 'Pastor'), ('Bishop', 'Bishop')
    ]
    
    title = models.CharField(max_length=20, choices=TITLE_CHOICES)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    surname = models.CharField(max_length=50)
    initials = models.CharField(max_length=10)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    preferred_name = models.CharField(max_length=50, blank=True)
    id_number = models.CharField(max_length=20, unique=True)
    passport_number = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField()
    race = models.CharField(max_length=20)
    disability = models.CharField(max_length=100, blank=True, null=True)
    
    # Contact Information
    email = models.EmailField(unique=True)
    cell = models.CharField(max_length=20)
    tel_work = models.CharField(max_length=20, blank=True)
    tel_home = models.CharField(max_length=20, blank=True)
    fax = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    
    # Address Information
    postal_address = models.TextField(blank=True)
    street_address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    province = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, default='South Africa')
    
    # Religious Information
    religious_affiliation = models.CharField(max_length=100, blank=True)
    
    # Language Information
    home_language = models.CharField(max_length=50, blank=True)
    other_languages = models.CharField(max_length=100, blank=True)
    
    # Professional Information
    highest_qualification = models.CharField(max_length=200, blank=True)
    qualification_date = models.DateField()
    qualification_institution = models.CharField(max_length=200)
    occupation = models.CharField(max_length=100, blank=True)
    work_description = models.TextField(blank=True)
    
    # Ministry Experience
    years_ministry = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(70)]
    )
    months_ministry = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(11)]
    )
    
    # Background Checks
    disciplinary_action = models.BooleanField(default=False)
    disciplinary_description = models.TextField(blank=True)
    felony_conviction = models.BooleanField(default=False)
    felony_description = models.TextField(blank=True)
    
    # Generic relation to documents
    documents = GenericRelation('Document')
    
    class Meta:
        abstract = True
        ordering = ['-created_at']
    
    def clean(self):
        """Custom validation logic"""
        super().clean()
        
        # Validate birth date
        if self.date_of_birth > timezone.now().date():
            raise ValidationError("Date of birth cannot be in the future.")
            
        # If disciplinary action is True, description is required
        if self.disciplinary_action and not self.disciplinary_description.strip():
            raise ValidationError("Disciplinary description is required when disciplinary action is marked.")
            
        # If felony conviction is True, description is required
        if self.felony_conviction and not self.felony_description.strip():
            raise ValidationError("Felony description is required when felony conviction is marked.")
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_display_name(self):
        return self.preferred_name if self.preferred_name else self.get_full_name()


# Council-specific models
class CGMPAffiliation(BaseAffiliation):
    """Council for General Ministry Professionals"""
    
    # CGMP-specific fields
    ordination_status = models.CharField(
        max_length=50,
        choices=[
            ('ordained', 'Ordained'),
            ('licensed', 'Licensed'), 
            ('certified', 'Certified'),
            ('trainee', 'Trainee')
        ]
    )
    ordination_date = models.DateField(null=True, blank=True)
    ordaining_body = models.CharField(max_length=200, blank=True)
    current_ministry_role = models.CharField(max_length=100, blank=True)
    congregation_name = models.CharField(max_length=200, blank=True)
    denomination = models.CharField(max_length=100, blank=True)
    
    # CGMP-specific ministry questions
    involved_pastoral = models.BooleanField(default=False)
    pastoral_responsibilities = models.TextField(blank=True)
    preaching_frequency = models.CharField(
        max_length=20,
        choices=[
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('occasionally', 'Occasionally'),
            ('rarely', 'Rarely')
        ],
        blank=True
    )
    
    # Professional development
    registered_elsewhere = models.BooleanField(default=False)
    other_registrations = models.TextField(blank=True)
    continuing_education = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "CGMP Affiliation"
        verbose_name_plural = "CGMP Affiliations"
    
    def __str__(self):
        return f"CGMP: {self.get_display_name()}"


class CPSCAffiliation(BaseAffiliation):
    """Council for Pastoral & Spiritual Care"""
    
    # CPSC-specific fields
    counseling_certification = models.CharField(
        max_length=100,
        choices=[
            ('cpe', 'Clinical Pastoral Education'),
            ('mft', 'Marriage and Family Therapy'),
            ('lpc', 'Licensed Professional Counselor'),
            ('other', 'Other'),
            ('none', 'None')
        ]
    )
    certification_body = models.CharField(max_length=200, blank=True)
    certification_date = models.DateField(null=True, blank=True)
    
    # Specialized training
    trauma_training = models.BooleanField(default=False)
    grief_counseling_training = models.BooleanField(default=False)
    addiction_counseling_training = models.BooleanField(default=False)
    family_counseling_training = models.BooleanField(default=False)
    
    # Practice details
    counseling_practice_type = models.CharField(
        max_length=50,
        choices=[
            ('private', 'Private Practice'),
            ('institutional', 'Institutional'),
            ('volunteer', 'Volunteer'),
            ('part_time', 'Part-time')
        ],
        blank=True
    )
    
    # Supervision
    clinical_supervision = models.BooleanField(default=False)
    supervisor_name = models.CharField(max_length=200, blank=True)
    supervision_hours = models.PositiveIntegerField(default=0)
    
    # Specializations
    specialization_areas = models.TextField(
        blank=True,
        help_text="List your areas of specialization in pastoral care"
    )
    
    # Ethics and liability
    professional_liability_insurance = models.BooleanField(default=False)
    insurance_provider = models.CharField(max_length=200, blank=True)
    
    class Meta:
        verbose_name = "CPSC Affiliation"
        verbose_name_plural = "CPSC Affiliations"
    
    def __str__(self):
        return f"CPSC: {self.get_display_name()}"


class CMTPAffiliation(BaseAffiliation):
    """Council for Ministry Training Providers"""
    
    # CMTP-specific fields
    institution_type = models.CharField(
        max_length=50,
        choices=[
            ('college', 'Bible College'),
            ('seminary', 'Seminary'),
            ('institute', 'Training Institute'),
            ('church', 'Church-based Training'),
            ('online', 'Online Platform'),
            ('independent', 'Independent Trainer')
        ]
    )
    
    institution_name = models.CharField(max_length=200)
    institution_address = models.TextField(blank=True)
    position_title = models.CharField(max_length=100)
    teaching_subjects = models.TextField(help_text="List subjects/courses you teach")
    
    # Qualifications for teaching
    teaching_qualification = models.CharField(max_length=200)
    teaching_experience_years = models.PositiveIntegerField(default=0)
    
    # Accreditation
    institution_accredited = models.BooleanField(default=False)
    accreditation_body = models.CharField(max_length=200, blank=True)
    accreditation_level = models.CharField(
        max_length=50,
        choices=[
            ('national', 'National'),
            ('regional', 'Regional'),
            ('international', 'International'),
            ('denominational', 'Denominational')
        ],
        blank=True
    )
    
    # Course delivery methods
    delivery_methods = models.CharField(
        max_length=100,
        choices=[
            ('in_person', 'In-person only'),
            ('online', 'Online only'),
            ('hybrid', 'Hybrid (In-person & Online)'),
            ('correspondence', 'Correspondence')
        ]
    )
    
    # Student capacity
    current_student_count = models.PositiveIntegerField(default=0)
    max_student_capacity = models.PositiveIntegerField(default=0)
    
    # Curriculum
    curriculum_type = models.CharField(
        max_length=50,
        choices=[
            ('diploma', 'Diploma Programs'),
            ('certificate', 'Certificate Programs'),
            ('degree', 'Degree Programs'),
            ('short_course', 'Short Courses'),
            ('workshops', 'Workshops/Seminars')
        ]
    )
    
    class Meta:
        verbose_name = "CMTP Affiliation"
        verbose_name_plural = "CMTP Affiliations"
    
    def __str__(self):
        return f"CMTP: {self.get_display_name()} - {self.institution_name}"


# Enhanced Document Model
class Document(models.Model):
    DOCUMENT_CATEGORIES = [
        ('supporting', 'Supporting Document'),
        ('payment', 'Proof of Payment'),
        ('qualification', 'Qualification Certificate'),
        ('id_document', 'ID Document'),
        ('ordination', 'Ordination Certificate'),
        ('certification', 'Professional Certification'),
        ('insurance', 'Insurance Certificate'),
        ('transcript', 'Academic Transcript'),
        ('reference', 'Reference Letter'),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    category = models.CharField(max_length=20, choices=DOCUMENT_CATEGORIES)
    file = models.FileField(upload_to='enrollments/docs/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Document metadata
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    
    # Verification status
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def save(self, *args, **kwargs):
        if self.file:
            self.original_filename = self.file.name
            self.file_size = self.file.size
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.get_category_display()} for {self.content_object}"


# Registration tracking model
class RegistrationSession(models.Model):
    """Track user registration sessions"""
    
    REGISTRATION_TYPES = [
        ('cgmp', 'CGMP - General Ministry Professionals'),
        ('cpsc', 'CPSC - Pastoral & Spiritual Care'),
        ('cmtp', 'CMTP - Ministry Training Providers'),
        ('student', 'Invited Affiliate'),
        ('provider', 'Training Provider'),
    ]
    
    session_key = models.CharField(max_length=255, unique=True)
    registration_type = models.CharField(max_length=20, choices=REGISTRATION_TYPES)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Registration Session: {self.registration_type} - {self.created_at}"