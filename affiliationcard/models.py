
import os
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import (
    MinValueValidator, MaxValueValidator, FileExtensionValidator
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db.models import Q

from PIL import Image
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile

User = get_user_model()


def get_card_photo_upload_path(instance, filename):
    """
    Generate secure upload path for affiliate photos.
    
    Path: affiliationcard/photos/{year}/{month}/{council}/{card_number}/{unique_filename}
    """
    council_code = instance.get_council_code().lower()
    year = timezone.now().year
    month = timezone.now().month
    
    # Generate unique filename to prevent conflicts and enhance security
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4().hex}_{secrets.token_hex(8)}.{ext}"
    
    return f"affiliationcard/photos/{year}/{month:02d}/{council_code}/{instance.card_number}/{unique_filename}"


def get_card_template_upload_path(instance, filename):
    """Generate upload path for card template assets."""
    council_code = instance.council.code.lower() if instance.council else 'default'
    ext = filename.split('.')[-1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    
    return f"affiliationcard/templates/{council_code}/{instance.template_type}/{unique_filename}"


# ============================================================================
# CORE CARD MODELS
# ============================================================================

class AffiliationCard(models.Model):
    """
    Digital Affiliation Card - Core model for digital identity cards.
    
    Features:
    - Polymorphic relationship to any application type
    - Secure QR code with verification tokens
    - Automatic expiry management
    - Comprehensive audit trail
    - Professional card numbering
    - Photo management with secure storage
    """
    
    # ========================================================================
    # POLYMORPHIC RELATIONSHIP TO APPLICATIONS
    # ========================================================================
    
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE,
        limit_choices_to=Q(
            app_label='enrollments',
            model__in=['associatedapplication', 'designatedapplication', 'studentapplication']
        ),
        help_text="Type of application this card is linked to"
    )
    object_id = models.PositiveBigIntegerField()
    application = GenericForeignKey('content_type', 'object_id')
    
    # ========================================================================
    # CARD IDENTIFICATION AND SECURITY
    # ========================================================================
    
    card_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Unique card reference number for public verification"
    )
    
    internal_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Internal UUID for secure operations"
    )
    
    verification_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Secure token for QR code verification"
    )
    
    qr_code_data = models.TextField(
        help_text="Complete QR code data payload (JSON)"
    )
    
    # ========================================================================
    # CARD STATUS AND LIFECYCLE
    # ========================================================================
    
    STATUS_CHOICES = [
        ('pending_assignment', 'Pending Assignment'),
        ('assigned', 'Assigned (Not Issued)'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('revoked', 'Revoked'),
        ('cancelled', 'Cancelled'),
    ]
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending_assignment',
        db_index=True
    )
    
    # ========================================================================
    # VALIDITY PERIODS
    # ========================================================================
    
    date_issued = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the card was officially issued to the affiliate"
    )
    
    date_expires = models.DateField(
        null=True,
        blank=True,
        help_text="Card expiry date (typically 1 year from issue)"
    )
    
    grace_period_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(365)],
        help_text="Grace period in days after expiry for renewal"
    )
    
    # ========================================================================
    # AFFILIATE INFORMATION (Cached for Performance)
    # ========================================================================
    
    affiliate_title = models.CharField(max_length=20)
    affiliate_full_name = models.CharField(max_length=300)
    affiliate_surname = models.CharField(max_length=150)
    affiliate_email = models.EmailField()
    affiliate_id_number = models.CharField(max_length=20)
    
    # Council and affiliation info
    council_code = models.CharField(max_length=10)
    council_name = models.CharField(max_length=200)
    affiliation_type = models.CharField(max_length=20)
    
    # Designation info (for designated affiliations)
    designation_category = models.CharField(max_length=100, blank=True)
    designation_subcategory = models.CharField(max_length=200, blank=True)
    
    # ========================================================================
    # VISUAL ELEMENTS
    # ========================================================================
    
    affiliate_photo = models.ImageField(
        upload_to=get_card_photo_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png'])],
        help_text="Affiliate photo for card display"
    )
    
    card_template = models.ForeignKey(
        'CardTemplate',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Visual template used for this card"
    )
    
    # Generated card images (cached for performance)
    card_image_front = models.ImageField(
        upload_to='affiliationcard/generated/front/',
        null=True,
        blank=True,
        help_text="Generated front side of the card"
    )
    
    card_image_back = models.ImageField(
        upload_to='affiliationcard/generated/back/',
        null=True,
        blank=True,
        help_text="Generated back side of the card"
    )
    
    # ========================================================================
    # ADMINISTRATIVE TRACKING
    # ========================================================================
    
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='assigned_cards',
        null=True,
        blank=True,
        help_text="Admin user who assigned this card"
    )
    
    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the card assignment was made"
    )
    
    issued_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='issued_cards',
        null=True,
        blank=True,
        help_text="Admin user who issued the card"
    )
    
    # ========================================================================
    # RENEWAL AND HISTORY
    # ========================================================================
    
    previous_card = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='renewed_cards',
        help_text="Previous version of this card (for renewals)"
    )
    
    renewal_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this card has been renewed"
    )
    
    # ========================================================================
    # METADATA
    # ========================================================================
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional metadata for analytics
    generation_time_seconds = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Time taken to generate card assets"
    )
    
    total_verifications = models.PositiveIntegerField(
        default=0,
        help_text="Total number of times this card has been verified"
    )
    
    last_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this card was scanned/verified"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Affiliation Card"
        verbose_name_plural = "Affiliation Cards"
        
        indexes = [
            models.Index(fields=['card_number']),
            models.Index(fields=['verification_token']),
            models.Index(fields=['status', 'date_expires']),
            models.Index(fields=['council_code', 'affiliation_type']),
            models.Index(fields=['affiliate_email']),
            models.Index(fields=['created_at']),
        ]
        
        constraints = [
            models.CheckConstraint(
                check=Q(date_expires__gt=models.F('date_issued')),
                name='valid_expiry_date'
            ),
            models.CheckConstraint(
                check=Q(renewal_count__gte=0),
                name='positive_renewal_count'
            ),
        ]
    
    def save(self, *args, **kwargs):
        """Enhanced save with auto-generation of secure tokens and card data."""
        
        # Generate card number if not set
        if not self.card_number:
            self.card_number = self.generate_card_number()
        
        # Generate verification token if not set
        if not self.verification_token:
            self.verification_token = self.generate_verification_token()
        
        # Cache affiliate information from application
        if self.application and not self.affiliate_full_name:
            self.cache_affiliate_data()
        
        # Generate QR code data
        if not self.qr_code_data or self.status == 'assigned':
            self.qr_code_data = self.generate_qr_code_data()
        
        # Set expiry date when issued
        if self.status == 'active' and not self.date_expires:
            self.date_expires = self.calculate_expiry_date()
        
        # Auto-expire if past expiry date
        if self.date_expires and timezone.now().date() > self.date_expires:
            if self.status == 'active':
                self.status = 'expired'
        
        super().save(*args, **kwargs)
    
    def clean(self):
        """Comprehensive validation."""
        errors = {}
        
        # Validate application exists and is approved
        if self.application:
            if not hasattr(self.application, 'status') or self.application.status != 'approved':
                errors['application'] = _("Card can only be assigned to approved applications")
        
        # Validate dates
        if self.date_issued and self.date_expires:
            if self.date_expires <= self.date_issued.date():
                errors['date_expires'] = _("Expiry date must be after issue date")
        
        # Validate status transitions
        if self.pk:  # Only for existing records
            old_instance = AffiliationCard.objects.get(pk=self.pk)
            if not self.is_valid_status_transition(old_instance.status, self.status):
                errors['status'] = _(f"Invalid status transition from {old_instance.status} to {self.status}")
        
        if errors:
            raise ValidationError(errors)
    
    def generate_card_number(self):
        """
        Generate unique card number.
        Format: {COUNCIL_CODE}C{AFFILIATION_CODE}{YEAR}{SEQUENCE}
        Example: CGMPCAST240001 (CGMP Council, Associated, 2024, sequence 1)
        """
        if not self.application:
            return f"TEMP{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        council_code = self.get_council_code()
        affiliation_code = self.get_affiliation_type_code()
        year = timezone.now().year % 100  # Last 2 digits
        
        # Get next sequence number for this council/type/year
        sequence = AffiliationCard.objects.filter(
            council_code=council_code,
            affiliation_type=affiliation_code,
            created_at__year=timezone.now().year
        ).count() + 1
        
        return f"{council_code}C{affiliation_code}{year:02d}{sequence:05d}"
    
    def generate_verification_token(self):
        """Generate cryptographically secure verification token."""
        # Combine multiple entropy sources
        timestamp = str(timezone.now().timestamp())
        random_data = secrets.token_hex(32)
        card_data = f"{self.card_number}{self.affiliate_email}"
        
        # Create secure hash
        combined = f"{timestamp}{random_data}{card_data}".encode('utf-8')
        return hashlib.sha256(combined).hexdigest()
    
    def generate_qr_code_data(self):
        """Generate QR code data payload."""
        import json
        
        base_url = getattr(settings, 'CARD_VERIFICATION_BASE_URL', 'https://acrp.org.za')
        
        qr_data = {
            'version': '1.0',
            'card_number': self.card_number,
            'verification_token': self.verification_token,
            'verification_url': f"{base_url}/verify/{self.verification_token}/",
            'direct_lookup_url': f"{base_url}/verify/lookup/",
            'issued_date': self.date_issued.isoformat() if self.date_issued else None,
            'expires_date': self.date_expires.isoformat() if self.date_expires else None,
            'council': self.council_code,
            'affiliate_name': f"{self.affiliate_title} {self.affiliate_full_name} {self.affiliate_surname}".strip(),
            'security_hash': self.generate_security_hash()
        }
        
        return json.dumps(qr_data, separators=(',', ':'))  # Compact JSON
    
    def generate_security_hash(self):
        """Generate security hash for QR code validation."""
        data = f"{self.card_number}{self.verification_token}{self.affiliate_id_number}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]
    
    def cache_affiliate_data(self):
        """Cache affiliate data from application for performance."""
        if not self.application:
            return
        
        app = self.application
        
        # Basic info
        self.affiliate_title = app.title
        self.affiliate_full_name = app.full_names
        self.affiliate_surname = app.surname
        self.affiliate_email = app.email
        self.affiliate_id_number = app.id_number
        
        # Council and affiliation
        self.council_code = app.get_council().code
        self.council_name = app.get_council().name
        self.affiliation_type = app.get_affiliation_type()
        
        # Designation info (if applicable)
        if hasattr(app, 'designation_category') and app.designation_category:
            self.designation_category = app.designation_category.name
            if hasattr(app, 'designation_subcategory') and app.designation_subcategory:
                self.designation_subcategory = app.designation_subcategory.name
    
    def calculate_expiry_date(self):
        """Calculate expiry date (1 year from issue date)."""
        if not self.date_issued:
            return None
        
        issue_date = self.date_issued.date() if isinstance(self.date_issued, datetime) else self.date_issued
        return issue_date + timedelta(days=365)
    
    def get_council_code(self):
        """Get council code from application."""
        if self.council_code:
            return self.council_code
        return self.application.get_council().code if self.application else 'UNK'
    
    def get_affiliation_type_code(self):
        """Get affiliation type code."""
        if self.affiliation_type:
            return self.affiliation_type[:2].upper()
        return self.application.get_affiliation_type()[:2].upper() if self.application else 'UN'
    
    def is_valid_status_transition(self, old_status, new_status):
        """Validate status transitions."""
        valid_transitions = {
            'pending_assignment': ['assigned', 'cancelled'],
            'assigned': ['active', 'cancelled'],
            'active': ['expired', 'suspended', 'revoked'],
            'expired': ['active'],  # Renewal
            'suspended': ['active', 'revoked'],
            'revoked': [],  # Terminal state
            'cancelled': [],  # Terminal state
        }
        
        return new_status in valid_transitions.get(old_status, [])
    
    def is_active(self):
        """Check if card is currently active and valid."""
        if self.status != 'active':
            return False
        
        if self.date_expires and timezone.now().date() > self.date_expires:
            return False
        
        return True
    
    def is_expired(self):
        """Check if card is expired."""
        if self.status == 'expired':
            return True
        
        if self.date_expires and timezone.now().date() > self.date_expires:
            return True
        
        return False
    
    def is_in_grace_period(self):
        """Check if card is in grace period after expiry."""
        if not self.is_expired():
            return False
        
        if not self.date_expires:
            return False
        
        grace_end = self.date_expires + timedelta(days=self.grace_period_days)
        return timezone.now().date() <= grace_end
    
    def days_until_expiry(self):
        """Get days until expiry (negative if expired)."""
        if not self.date_expires:
            return None
        
        delta = self.date_expires - timezone.now().date()
        return delta.days
    
    def get_verification_url(self):
        """Get full verification URL."""
        return reverse('affiliationcard:verify_token', args=[self.verification_token])
    
    def get_lookup_url(self):
        """Get card lookup URL."""
        return reverse('affiliationcard:verify_lookup')
    
    def assign_card(self, assigned_by=None):
        """Assign card to affiliate."""
        if self.status != 'pending_assignment':
            raise ValidationError("Card can only be assigned from pending_assignment status")
        
        self.status = 'assigned'
        self.assigned_by = assigned_by
        self.assigned_at = timezone.now()
        self.save()
    
    def issue_card(self, issued_by=None):
        """Issue card to affiliate (activates the card)."""
        if self.status != 'assigned':
            raise ValidationError("Card must be assigned before it can be issued")
        
        self.status = 'active'
        self.issued_by = issued_by
        self.date_issued = timezone.now()
        self.date_expires = self.calculate_expiry_date()
        self.save()
    
    def suspend_card(self, reason=''):
        """Suspend the card."""
        if self.status not in ['active']:
            raise ValidationError("Only active cards can be suspended")
        
        self.status = 'suspended'
        self.save()
        
        # Log the suspension
        CardStatusChange.objects.create(
            card=self,
            old_status='active',
            new_status='suspended',
            reason=reason,
            changed_by=None  # Set in view
        )
    
    def revoke_card(self, reason=''):
        """Permanently revoke the card."""
        if self.status in ['revoked', 'cancelled']:
            raise ValidationError("Card is already revoked or cancelled")
        
        old_status = self.status
        self.status = 'revoked'
        self.save()
        
        # Log the revocation
        CardStatusChange.objects.create(
            card=self,
            old_status=old_status,
            new_status='revoked',
            reason=reason,
            changed_by=None  # Set in view
        )
    
    def renew_card(self, renewed_by=None):
        """Create a renewal of this card."""
        if not self.is_expired() and not self.is_in_grace_period():
            raise ValidationError("Card can only be renewed if expired or in grace period")
        
        # Create new card as renewal
        new_card = AffiliationCard.objects.create(
            content_type=self.content_type,
            object_id=self.object_id,
            previous_card=self,
            renewal_count=self.renewal_count + 1,
            assigned_by=renewed_by,
            assigned_at=timezone.now()
        )
        
        # Update old card status
        self.status = 'expired'
        self.save()
        
        return new_card
    
    def increment_verification_count(self):
        """Increment verification counter."""
        self.total_verifications = models.F('total_verifications') + 1
        self.last_verified_at = timezone.now()
        self.save(update_fields=['total_verifications', 'last_verified_at'])
    
    def get_display_name(self):
        """Get formatted display name."""
        return f"{self.affiliate_title} {self.affiliate_full_name} {self.affiliate_surname}".strip()
    
    def get_card_type_display(self):
        """Get formatted card type."""
        if self.designation_subcategory:
            return f"{self.designation_subcategory}"
        elif self.designation_category:
            return f"{self.designation_category}"
        else:
            return f"{self.affiliation_type.title()} Affiliate"
    
    def __str__(self):
        return f"Card {self.card_number} - {self.get_display_name()} ({self.status})"


# ============================================================================
# CARD TEMPLATE SYSTEM
# ============================================================================

class CardTemplate(models.Model):
    """
    Card visual templates for different councils and types.
    
    Supports customizable layouts, colors, logos, and styling
    for professional-looking digital cards.
    """
    
    TEMPLATE_TYPES = [
        ('default', 'Default Template'),
        ('council_specific', 'Council Specific'),
        ('designation_specific', 'Designation Specific'),
        ('custom', 'Custom Template'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    
    # Council association
    council = models.ForeignKey(
        'enrollments.Council',
        on_delete=models.CASCADE,
        related_name='card_templates',
        null=True,
        blank=True,
        help_text="Leave blank for universal templates"
    )
    
    # Template assets
    logo_image = models.ImageField(
        upload_to=get_card_template_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'svg'])],
        help_text="Primary logo for the card"
    )
    
    background_image = models.ImageField(
        upload_to=get_card_template_upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg'])],
        help_text="Background image for the card"
    )
    
    # Color scheme
    primary_color = models.CharField(
        max_length=7,
        default='#1f2937',
        help_text="Primary color (hex format)"
    )
    secondary_color = models.CharField(
        max_length=7,
        default='#6b7280',
        help_text="Secondary color (hex format)"
    )
    accent_color = models.CharField(
        max_length=7,
        default='#3b82f6',
        help_text="Accent color (hex format)"
    )
    text_color = models.CharField(
        max_length=7,
        default='#ffffff',
        help_text="Text color (hex format)"
    )
    
    # Layout configuration (JSON)
    layout_config = models.JSONField(
        default=dict,
        help_text="Layout configuration for card elements"
    )
    
    # Template status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Use as default template for this council"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        ordering = ['council__code', 'name']
        verbose_name = "Card Template"
        verbose_name_plural = "Card Templates"
        
        constraints = [
            models.UniqueConstraint(
                fields=['council', 'is_default'],
                condition=Q(is_default=True),
                name='unique_default_per_council'
            ),
        ]
    
    def clean(self):
        """Validate template configuration."""
        # Validate hex colors
        color_fields = ['primary_color', 'secondary_color', 'accent_color', 'text_color']
        for field in color_fields:
            color = getattr(self, field)
            if not color.startswith('#') or len(color) != 7:
                raise ValidationError({field: _("Must be a valid hex color (e.g., #1f2937)")})
    
    def get_layout_config(self):
        """Get layout configuration with defaults."""
        default_config = {
            'card_width': 850,
            'card_height': 540,
            'photo_size': 120,
            'photo_position': {'x': 50, 'y': 50},
            'logo_size': 80,
            'logo_position': {'x': 700, 'y': 30},
            'qr_size': 100,
            'qr_position': {'x': 700, 'y': 400},
            'font_sizes': {
                'name': 24,
                'title': 16,
                'council': 14,
                'card_number': 12,
                'dates': 10
            }
        }
        
        # Merge with stored config
        config = default_config.copy()
        config.update(self.layout_config)
        return config
    
    def __str__(self):
        council_name = self.council.code if self.council else 'Universal'
        return f"{self.name} ({council_name})"


# ============================================================================
# AUDIT AND TRACKING MODELS
# ============================================================================

class CardVerification(models.Model):
    """
    Track card verification events (QR scans, manual lookups).
    
    Provides audit trail and analytics for card usage.
    """
    
    VERIFICATION_TYPES = [
        ('qr_scan', 'QR Code Scan'),
        ('manual_lookup', 'Manual Card Number Lookup'),
        ('api_verification', 'API Verification'),
        ('bulk_verification', 'Bulk Verification'),
    ]
    
    card = models.ForeignKey(
        AffiliationCard,
        on_delete=models.CASCADE,
        related_name='verifications'
    )
    
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPES)
    
    # Request details
    verified_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    referer = models.URLField(blank=True)
    
    # Geolocation (if available)
    country_code = models.CharField(max_length=2, blank=True)
    region = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    # Verification result
    was_successful = models.BooleanField(default=True)
    card_status_at_time = models.CharField(max_length=20)
    error_message = models.TextField(blank=True)
    
    # Additional context
    verified_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="If verified by a logged-in user"
    )
    
    verification_purpose = models.CharField(
        max_length=100,
        blank=True,
        help_text="Purpose of verification (e.g., event entry, service request)"
    )
    
    class Meta:
        ordering = ['-verified_at']
        verbose_name = "Card Verification"
        verbose_name_plural = "Card Verifications"
        
        indexes = [
            models.Index(fields=['verified_at']),
            models.Index(fields=['card', 'verified_at']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['was_successful']),
        ]
    
    def __str__(self):
        return f"Verification of {self.card.card_number} at {self.verified_at}"



class CardDelivery(models.Model):
    """
    Track card delivery via email and download events.
    
    Monitors the delivery lifecycle from email sending to final download.
    """
    
    DELIVERY_TYPES = [
        ('email_pdf', 'Email PDF Attachment'),
        ('email_link', 'Email Download Link'),
        ('sms_link', 'SMS Download Link'),
        ('direct_download', 'Direct Download'),
        ('api_delivery', 'API Delivery'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),  # Added for compatibility
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('downloaded', 'Downloaded'),
        ('completed', 'Completed'),  # Added for compatibility
        ('ready_for_download', 'Ready for Download'),  # Added for compatibility
        ('failed', 'Failed'),
        ('bounced', 'Bounced'),
    ]
    
    card = models.ForeignKey(
        'AffiliationCard',  # Use string reference to avoid import issues
        on_delete=models.CASCADE,
        related_name='deliveries'
    )
    
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Recipient details
    recipient_email = models.EmailField()
    recipient_phone = models.CharField(max_length=20, blank=True)
    recipient_name = models.CharField(max_length=300)
    
    # Delivery metadata
    initiated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    initiated_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)  # Added for compatibility
    
    # Error tracking
    error_message = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)  # Added for enhanced error tracking
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    
    # Email tracking
    email_message_id = models.CharField(max_length=255, blank=True)
    mailjet_message_id = models.CharField(max_length=255, blank=True)  # Added for Mailjet integration
    bounce_reason = models.TextField(blank=True)
    
    # Enhanced email customization fields
    email_subject = models.CharField(max_length=200, blank=True, help_text="Custom email subject line")
    email_message = models.TextField(blank=True, help_text="Additional custom message for email")
    delivery_notes = models.TextField(blank=True, help_text="Internal delivery notes")
    
    # Download tracking
    download_token = models.CharField(max_length=64, blank=True, unique=True)
    download_expires_at = models.DateTimeField(null=True, blank=True)
    download_count = models.PositiveIntegerField(default=0)
    max_downloads = models.PositiveIntegerField(default=5)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)  # Added for tracking
    
    # File details
    file_format = models.CharField(
        max_length=10,
        choices=[('pdf', 'PDF'), ('png', 'PNG'), ('jpg', 'JPEG')],
        default='pdf'
    )
    file_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)  # Alias for compatibility
    generated_filename = models.CharField(max_length=255, blank=True, help_text="Generated filename for the card file")
    
    class Meta:
        ordering = ['-initiated_at']
        verbose_name = "Card Delivery"
        verbose_name_plural = "Card Deliveries"
        
        indexes = [
            models.Index(fields=['initiated_at']),
            models.Index(fields=['status']),
            models.Index(fields=['download_token']),
            models.Index(fields=['recipient_email']),
        ]
    
    def save(self, *args, **kwargs):
        """Generate download token if needed and set defaults."""
        # Generate download token for delivery types that need it
        if self.delivery_type in ['email_link', 'sms_link', 'direct_download'] and not self.download_token:
            self.download_token = secrets.token_urlsafe(32)
            
        # Set download expiry if token exists but no expiry set
        if self.download_token and not self.download_expires_at:
            # Set expiry to 30 days from now for email/sms links, 24 hours for direct download
            if self.delivery_type == 'direct_download':
                self.download_expires_at = timezone.now() + timedelta(hours=24)
            else:
                self.download_expires_at = timezone.now() + timedelta(days=30)
        
        # Ensure compatibility between file_size fields
        if self.file_size and not self.file_size_bytes:
            self.file_size_bytes = self.file_size
        elif self.file_size_bytes and not self.file_size:
            self.file_size = self.file_size_bytes
        
        super().save(*args, **kwargs)
    
    def is_download_valid(self):
        """Check if download is still valid."""
        if not self.download_token:
            return False
        
        # Check if expired
        if self.download_expires_at and timezone.now() > self.download_expires_at:
            return False
        
        # Check if max downloads exceeded
        if self.download_count >= self.max_downloads:
            return False
        
        return True
    
    def record_download(self):
        """Record a download event."""
        if not self.is_download_valid():
            raise ValidationError("Download is no longer valid")
        
        self.download_count += 1
        self.last_downloaded_at = timezone.now()
        
        # Update status if this is the first download
        if self.status not in ['downloaded', 'completed']:
            self.status = 'downloaded'
            if not self.downloaded_at:
                self.downloaded_at = timezone.now()
        
        self.save()
    
    def get_download_url(self):
        """Get download URL."""
        if not self.download_token:
            return None
        
        return reverse('affiliationcard:download_card', args=[self.download_token])
    
    def get_status_display_color(self):
        """Get CSS color class for status display."""
        status_colors = {
            'pending': 'text-yellow-600 bg-yellow-100',
            'processing': 'text-blue-600 bg-blue-100',
            'sending': 'text-blue-600 bg-blue-100',
            'sent': 'text-green-600 bg-green-100',
            'delivered': 'text-green-600 bg-green-100',
            'completed': 'text-green-600 bg-green-100',
            'downloaded': 'text-green-600 bg-green-100',
            'ready_for_download': 'text-indigo-600 bg-indigo-100',
            'failed': 'text-red-600 bg-red-100',
            'bounced': 'text-red-600 bg-red-100',
        }
        return status_colors.get(self.status, 'text-gray-600 bg-gray-100')
    
    def days_until_expiry(self):
        """Get days until download expires."""
        if not self.download_expires_at:
            return None
        
        delta = self.download_expires_at.date() - timezone.now().date()
        return delta.days if delta.days >= 0 else 0
    
    def is_expired(self):
        """Check if delivery/download is expired."""
        return not self.is_download_valid() and self.download_expires_at and timezone.now() > self.download_expires_at
    
    def get_delivery_method_display(self):
        """Get human-readable delivery method display."""
        method_display = {
            'email_pdf': 'Email with PDF Attachment',
            'email_link': 'Email with Download Link',
            'sms_link': 'SMS with Download Link',
            'direct_download': 'Direct Download',
            'api_delivery': 'API Delivery',
        }
        return method_display.get(self.delivery_type, self.delivery_type.title())
    
    def __str__(self):
        return f"Delivery of {self.card.card_number} to {self.recipient_email} ({self.status})"
class CardStatusChange(models.Model):
    """
    Audit trail for card status changes.
    
    Tracks all status transitions with timestamps and reasons.
    """
    
    card = models.ForeignKey(
        AffiliationCard,
        on_delete=models.CASCADE,
        related_name='status_changes'
    )
    
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    reason = models.TextField(
        blank=True,
        help_text="Reason for status change"
    )
    
    # System context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-changed_at']
        verbose_name = "Card Status Change"
        verbose_name_plural = "Card Status Changes"
        
        indexes = [
            models.Index(fields=['card', 'changed_at']),
            models.Index(fields=['changed_at']),
            models.Index(fields=['new_status']),
        ]
    
    def __str__(self):
        return f"{self.card.card_number}: {self.old_status} → {self.new_status}"


# ============================================================================
# SYSTEM CONFIGURATION
# ============================================================================

class CardSystemSettings(models.Model):
    """
    Global system settings for card management.
    
    Centralizes configuration for card generation, security, and features.
    """
    
    # Card generation settings
    default_validity_days = models.PositiveIntegerField(
        default=365,
        help_text="Default card validity period in days"
    )
    
    grace_period_days = models.PositiveIntegerField(
        default=30,
        help_text="Grace period after expiry for renewals"
    )
    
    # Security settings
    require_photo = models.BooleanField(
        default=False,
        help_text="Require affiliate photo for card generation"
    )
    
    max_verification_attempts = models.PositiveIntegerField(
        default=10,
        help_text="Maximum verification attempts per IP per hour"
    )
    
    # Email settings
    card_delivery_from_email = models.EmailField(
        default='noreply@acrp.org.za',
        help_text="From email address for card deliveries"
    )
    
    email_template_subject = models.CharField(
        max_length=200,
        default='Your ACRP Digital Affiliation Card',
        help_text="Email subject template"
    )
    
    # File generation settings
    default_card_format = models.CharField(
        max_length=10,
        choices=[('pdf', 'PDF'), ('png', 'PNG'), ('jpg', 'JPEG')],
        default='pdf'
    )
    
    card_image_quality = models.PositiveIntegerField(
        default=95,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Image quality for generated cards (1-100)"
    )
    
    # Feature flags
    enable_qr_codes = models.BooleanField(default=True)
    enable_email_delivery = models.BooleanField(default=True)
    enable_bulk_operations = models.BooleanField(default=True)
    enable_api_access = models.BooleanField(default=False)
    
    # Maintenance
    auto_expire_cards = models.BooleanField(
        default=True,
        help_text="Automatically expire cards past their expiry date"
    )
    
    cleanup_old_verifications_days = models.PositiveIntegerField(
        default=730,  # 2 years
        help_text="Delete verification records older than this many days"
    )
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = "Card System Settings"
        verbose_name_plural = "Card System Settings"
    
    def save(self, *args, **kwargs):
        """Ensure only one settings instance exists."""
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        """Get or create system settings."""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def __str__(self):
        return "Card System Settings"