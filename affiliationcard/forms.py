import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db.models import Q
from django.conf import settings

from PIL import Image
from io import BytesIO

from .models import (
    AffiliationCard, CardTemplate, CardVerification, CardDelivery,
    CardStatusChange, CardSystemSettings
)

User = get_user_model()


# ============================================================================
# ADMIN CARD MANAGEMENT FORMS
# ============================================================================

class CardAssignmentForm(forms.Form):
    """
    Form for admin to assign digital cards to approved applications.
    
    This is the core form used when admin clicks "Assign Digital Card"
    during the application review process.
    """
    
    # Application selection (will be pre-populated in most cases)
    application_type = forms.ChoiceField(
        choices=[
            ('enrollments.associatedapplication', 'Associated Application'),
            ('enrollments.designatedapplication', 'Designated Application'),
            ('enrollments.studentapplication', 'Student Application'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-bs-toggle': 'tooltip',
            'title': 'Type of application for card assignment'
        })
    )
    
    application_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        help_text="ID of the application to assign card to"
    )
    
    # Card configuration
    card_template = forms.ModelChoiceField(
        queryset=CardTemplate.objects.none(),  # Will be populated in __init__
        required=False,
        empty_label="Use default template",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'data-bs-toggle': 'tooltip',
            'title': 'Visual template for the card'
        }),
        help_text="Choose a visual template for the card. Leave blank to use default."
    )
    
    # Validity configuration
    validity_days = forms.IntegerField(
        initial=365,
        min_value=30,
        max_value=1095,  # 3 years max
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '30',
            'max': '1095',
            'step': '1'
        }),
        help_text="Number of days the card will be valid (30-1095 days)"
    )
    
    grace_period_days = forms.IntegerField(
        initial=30,
        min_value=0,
        max_value=90,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '90',
            'step': '1'
        }),
        help_text="Grace period in days after expiry for renewal (0-90 days)"
    )
    
    # Immediate issuance option
    issue_immediately = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'data-bs-toggle': 'tooltip',
            'title': 'Issue card immediately after assignment'
        }),
        help_text="Check to activate the card immediately after assignment"
    )
    
    # Delivery options
    send_email_notification = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Send email notification to affiliate when card is ready"
    )
    
    # Admin notes
    assignment_notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional notes about this card assignment...'
        }),
        help_text="Internal notes for this card assignment"
    )
    
    def __init__(self, *args, **kwargs):
        """Initialize form with dynamic querysets."""
        self.council = kwargs.pop('council', None)
        self.application = kwargs.pop('application', None)
        super().__init__(*args, **kwargs)
        
        # Set up card template queryset based on council
        if self.council:
            self.fields['card_template'].queryset = CardTemplate.objects.filter(
                Q(council=self.council) | Q(council__isnull=True),
                is_active=True
            ).order_by('council__code', 'name')
        else:
            self.fields['card_template'].queryset = CardTemplate.objects.filter(
                is_active=True
            ).order_by('council__code', 'name')
        
        # Pre-populate fields if application is provided
        if self.application:
            self.fields['application_id'].initial = self.application.pk
            
            # Set application type
            content_type = ContentType.objects.get_for_model(self.application)
            self.fields['application_type'].initial = f"{content_type.app_label}.{content_type.model}"
    
    def clean(self):
        """Validate the card assignment."""
        cleaned_data = super().clean()
        
        # Validate application exists and is approved
        app_type = cleaned_data.get('application_type')
        app_id = cleaned_data.get('application_id')
        
        if app_type and app_id:
            try:
                content_type = ContentType.objects.get(
                    app_label=app_type.split('.')[0],
                    model=app_type.split('.')[1]
                )
                application = content_type.get_object_for_this_type(pk=app_id)
                
                # Check if application is approved
                if not hasattr(application, 'status') or application.status != 'approved':
                    raise ValidationError("Card can only be assigned to approved applications")
                
                # Check if card already exists
                if AffiliationCard.objects.filter(
                    content_type=content_type,
                    object_id=app_id,
                    status__in=['assigned', 'active']
                ).exists():
                    raise ValidationError("An active card already exists for this application")
                
                cleaned_data['application'] = application
                
            except (ContentType.DoesNotExist, application.DoesNotExist):
                raise ValidationError("Invalid application specified")
        
        # Validate template is appropriate for council
        template = cleaned_data.get('card_template')
        if template and template.council and self.council:
            if template.council != self.council:
                raise ValidationError("Selected template is not compatible with this council")
        
        return cleaned_data


class CardPhotoUploadForm(forms.Form):
    """
    Form for uploading/updating affiliate photos on cards.
    
    Handles image validation, processing, and optimization.
    """
    
    photo = forms.ImageField(
        validators=[],  # Custom validation in clean_photo
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/jpg,image/png',
            'data-max-size': '5MB'
        }),
        help_text="Upload a clear, professional photo (JPEG/PNG, max 5MB)"
    )
    
    # Photo processing options
    auto_crop = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Automatically crop photo to square aspect ratio"
    )
    
    enhance_quality = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Apply automatic quality enhancement"
    )
    
    def clean_photo(self):
        """Validate and process the uploaded photo."""
        photo = self.cleaned_data.get('photo')
        
        if not photo:
            return photo
        
        # Validate file size (5MB max)
        if photo.size > 5 * 1024 * 1024:
            raise ValidationError("Photo file size cannot exceed 5MB")
        
        # Validate image format and dimensions
        try:
            image = Image.open(photo)
            
            # Validate format
            if image.format not in ['JPEG', 'PNG']:
                raise ValidationError("Photo must be in JPEG or PNG format")
            
            # Validate dimensions (minimum requirements)
            min_dimension = 200
            if image.width < min_dimension or image.height < min_dimension:
                raise ValidationError(f"Photo must be at least {min_dimension}x{min_dimension} pixels")
            
            # Validate aspect ratio (should be roughly square for best results)
            aspect_ratio = image.width / image.height
            if not (0.7 <= aspect_ratio <= 1.4):
                # Will be auto-cropped if auto_crop is enabled
                if not self.cleaned_data.get('auto_crop'):
                    raise ValidationError(
                        "Photo should have a square or near-square aspect ratio. "
                        "Enable auto-crop or upload a different photo."
                    )
            
            # Reset file pointer
            photo.seek(0)
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError("Invalid image file. Please upload a valid JPEG or PNG image.")
        
        return photo


class CardStatusUpdateForm(forms.Form):
    """
    Form for updating card status (suspend, revoke, reactivate).
    
    Used by admins for card lifecycle management.
    """
    
    STATUS_CHOICES = [
        ('pending_assignment', 'Pending Assignment'),
        ('assigned', 'Assigned (Not Issued)'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('revoked', 'Revoked'),
        ('cancelled', 'Cancelled'),
    ]
    
    new_status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text="Select the new status for the card"
    )
    
    reason = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Provide a reason for this status change...'
        }),
        help_text="Explain why the card status is being changed"
    )
    
    notify_affiliate = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Send email notification to affiliate about status change"
    )
    
    def __init__(self, *args, **kwargs):
        """Initialize form with current card status."""
        self.card = kwargs.pop('card', None)
        super().__init__(*args, **kwargs)
        
        if self.card:
            # Filter available status choices based on current status
            current_status = self.card.status
            
            valid_transitions = {
                'pending_assignment': [('assigned', 'Assign Card'), ('cancelled', 'Cancel Card')],
                'assigned': [('active', 'Activate Card'), ('cancelled', 'Cancel Card')],
                'active': [('suspended', 'Suspend Card'), ('revoked', 'Revoke Card')],
                'suspended': [('active', 'Reactivate Card'), ('revoked', 'Revoke Card')],
                'expired': [('active', 'Renew Card')],
            }
            
            if current_status in valid_transitions:
                self.fields['new_status'].choices = valid_transitions[current_status]
    
    def clean(self):
        """Validate status transition."""
        cleaned_data = super().clean()
        
        if self.card:
            new_status = cleaned_data.get('new_status')
            if not self.card.is_valid_status_transition(self.card.status, new_status):
                raise ValidationError(
                    f"Cannot change status from {self.card.get_status_display()} to "
                    f"{dict(self.STATUS_CHOICES).get(new_status, new_status)}"
                )
        
        return cleaned_data


class BulkCardOperationForm(forms.Form):
    """
    Form for bulk operations on multiple cards.
    
    Allows admins to perform batch operations efficiently.
    """
    
    OPERATION_CHOICES = [
        ('assign', 'Assign Cards'),
        ('issue', 'Issue Cards'),
        ('suspend', 'Suspend Cards'),
        ('send_email', 'Send Email Notifications'),
        ('regenerate', 'Regenerate Card Images'),
    ]
    
    operation = forms.ChoiceField(
        choices=OPERATION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text="Select the operation to perform on selected cards"
    )
    
    # Card selection
    card_ids = forms.CharField(
        widget=forms.HiddenInput(),
        help_text="Comma-separated list of card IDs"
    )
    
    # Operation-specific fields
    reason = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional reason for this bulk operation...'
        }),
        help_text="Reason for performing this bulk operation"
    )
    
    send_notifications = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Send email notifications to affected affiliates"
    )
    
    def clean_card_ids(self):
        """Validate card IDs."""
        card_ids_str = self.cleaned_data.get('card_ids', '')
        
        if not card_ids_str:
            raise ValidationError("No cards selected for bulk operation")
        
        try:
            card_ids = [int(id.strip()) for id in card_ids_str.split(',') if id.strip()]
        except ValueError:
            raise ValidationError("Invalid card IDs provided")
        
        if not card_ids:
            raise ValidationError("No valid card IDs provided")
        
        # Validate that cards exist
        existing_cards = AffiliationCard.objects.filter(id__in=card_ids)
        if existing_cards.count() != len(card_ids):
            raise ValidationError("Some selected cards do not exist")
        
        return card_ids


# ============================================================================
# PUBLIC VERIFICATION FORMS
# ============================================================================

class CardLookupForm(forms.Form):
    """
    Public form for looking up cards by card number.
    
    Used on the public verification page where people can manually
    enter card numbers to verify affiliate status.
    """
    
    card_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter card number (e.g., CGMPCAST240001)',
            'autocomplete': 'off',
            'style': 'text-transform: uppercase; letter-spacing: 1px;'
        }),
        help_text="Enter the card number exactly as shown on the affiliation card"
    )
    
    # Optional verification context
    verification_purpose = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Purpose of verification (optional)'
        }),
        help_text="Optional: Describe why you're verifying this card"
    )
    
    def clean_card_number(self):
        """Validate and normalize card number."""
        card_number = self.cleaned_data.get('card_number', '').strip().upper()
        
        if not card_number:
            raise ValidationError("Card number is required")
        
        # Basic format validation
        if len(card_number) < 10:
            raise ValidationError("Card number appears to be too short")
        
        if len(card_number) > 20:
            raise ValidationError("Card number appears to be too long")
        
        # Remove spaces and normalize
        card_number = card_number.replace(' ', '').replace('-', '')
        
        return card_number


class QRVerificationForm(forms.Form):
    """
    Form for processing QR code verification data.
    
    Handles the JSON payload from scanned QR codes.
    """
    
    qr_data = forms.CharField(
        widget=forms.HiddenInput(),
        help_text="QR code data payload"
    )
    
    verification_token = forms.CharField(
        max_length=64,
        required=False,
        widget=forms.HiddenInput(),
        help_text="Verification token from QR code"
    )
    
    def clean_qr_data(self):
        """Validate and parse QR code data."""
        qr_data_str = self.cleaned_data.get('qr_data', '')
        
        if not qr_data_str:
            raise ValidationError("QR code data is required")
        
        try:
            qr_data = json.loads(qr_data_str)
        except json.JSONDecodeError:
            raise ValidationError("Invalid QR code data format")
        
        # Validate required fields
        required_fields = ['version', 'card_number', 'verification_token']
        for field in required_fields:
            if field not in qr_data:
                raise ValidationError(f"QR code missing required field: {field}")
        
        # Validate version compatibility
        if qr_data.get('version') != '1.0':
            raise ValidationError("Unsupported QR code version")
        
        return qr_data


# ============================================================================
# CARD DELIVERY FORMS
# ============================================================================

class CardDeliveryForm(forms.Form):
    """
    Form for configuring card delivery options.
    
    Used when sending cards to affiliates via email or other methods.
    """
    
    DELIVERY_METHODS = [
        ('email_pdf', 'Email PDF Attachment'),
        ('email_link', 'Email Download Link'),
        ('direct_download', 'Generate Download Link'),
    ]
    
    delivery_method = forms.ChoiceField(
        choices=DELIVERY_METHODS,
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        help_text="Choose how to deliver the card to the affiliate"
    )
    
    # Recipient details
    recipient_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'affiliate@example.com'
        }),
        help_text="Email address to send the card to"
    )
    
    recipient_name = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Affiliate Name'
        }),
        help_text="Full name of the recipient"
    )
    
    # Email customization
    email_subject = forms.CharField(
        max_length=200,
        initial='Your ACRP Digital Affiliation Card',
        widget=forms.TextInput(attrs={
            'class': 'form-control'
        }),
        help_text="Email subject line"
    )
    
    email_message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Enter a personal message for the affiliate...'
        }),
        required=False,
        help_text="Optional personal message to include in the email"
    )
    
    # File format options
    file_format = forms.ChoiceField(
        choices=[
            ('pdf', 'PDF Document'),
            ('png', 'PNG Image'),
            ('jpg', 'JPEG Image'),
        ],
        initial='pdf',
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text="Format for the card file"
    )
    
    # Delivery options
    priority = forms.ChoiceField(
        choices=[
            ('normal', 'Normal Priority'),
            ('high', 'High Priority'),
            ('urgent', 'Urgent'),
        ],
        initial='normal',
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        help_text="Delivery priority level"
    )
    
    def __init__(self, *args, **kwargs):
        """Initialize form with card data."""
        self.card = kwargs.pop('card', None)
        super().__init__(*args, **kwargs)
        
        if self.card:
            # Pre-populate recipient details from card
            self.fields['recipient_email'].initial = self.card.affiliate_email
            self.fields['recipient_name'].initial = self.card.get_display_name()


class CardDownloadForm(forms.Form):
    """
    Form for card download requests.
    
    Handles secure download token validation and options.
    """
    
    download_token = forms.CharField(
        max_length=64,
        widget=forms.HiddenInput()
    )
    
    file_format = forms.ChoiceField(
        choices=[
            ('pdf', 'PDF Document'),
            ('png', 'High Quality Image (PNG)'),
            ('jpg', 'Compressed Image (JPEG)'),
        ],
        initial='pdf',
        widget=forms.RadioSelect(attrs={
            'class': 'form-check-input'
        }),
        help_text="Choose the format for your card download"
    )
    
    agree_terms = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="I agree that this card is for personal use only and will not be shared or duplicated"
    )
    
    def clean_download_token(self):
        """Validate download token."""
        token = self.cleaned_data.get('download_token')
        
        if not token:
            raise ValidationError("Download token is required")
        
        try:
            delivery = CardDelivery.objects.get(download_token=token)
            
            if not delivery.is_download_valid():
                raise ValidationError("Download link has expired or reached maximum usage")
            
            self.delivery = delivery
            return token
            
        except CardDelivery.DoesNotExist:
            raise ValidationError("Invalid download token")


# ============================================================================
# TEMPLATE AND SYSTEM MANAGEMENT FORMS
# ============================================================================

class CardTemplateForm(forms.ModelForm):
    """
    Form for creating and editing card templates.
    
    Used by admins to manage visual templates for different councils.
    """
    
    class Meta:
        model = CardTemplate
        fields = [
            'name', 'description', 'template_type', 'council',
            'logo_image', 'background_image',
            'primary_color', 'secondary_color', 'accent_color', 'text_color',
            'is_active', 'is_default'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'template_type': forms.Select(attrs={'class': 'form-select'}),
            'council': forms.Select(attrs={'class': 'form-select'}),
            'logo_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'background_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'accent_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'text_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    # Layout configuration as JSON field
    layout_config_json = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 10,
            'data-language': 'json'
        }),
        required=False,
        help_text="JSON configuration for card layout (advanced users only)"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate layout config JSON
        if self.instance and self.instance.layout_config:
            self.fields['layout_config_json'].initial = json.dumps(
                self.instance.layout_config, indent=2
            )
    
    def clean_layout_config_json(self):
        """Validate JSON configuration."""
        json_str = self.cleaned_data.get('layout_config_json', '').strip()
        
        if not json_str:
            return {}
        
        try:
            config = json.loads(json_str)
            if not isinstance(config, dict):
                raise ValidationError("Layout configuration must be a JSON object")
            return config
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def save(self, commit=True):
        """Save template with layout configuration."""
        instance = super().save(commit=False)
        
        # Set layout configuration from JSON field
        layout_config = self.cleaned_data.get('layout_config_json', {})
        instance.layout_config = layout_config
        
        if commit:
            instance.save()
        
        return instance


class SystemSettingsForm(forms.ModelForm):
    """
    Form for managing card system settings.
    
    Used by system administrators to configure global settings.
    """
    
    class Meta:
        model = CardSystemSettings
        fields = [
            'default_validity_days', 'grace_period_days',
            'require_photo', 'max_verification_attempts',
            'card_delivery_from_email', 'email_template_subject',
            'default_card_format', 'card_image_quality',
            'enable_qr_codes', 'enable_email_delivery',
            'enable_bulk_operations', 'enable_api_access',
            'auto_expire_cards', 'cleanup_old_verifications_days'
        ]
        widgets = {
            'default_validity_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'grace_period_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'require_photo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_verification_attempts': forms.NumberInput(attrs={'class': 'form-control'}),
            'card_delivery_from_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'email_template_subject': forms.TextInput(attrs={'class': 'form-control'}),
            'default_card_format': forms.Select(attrs={'class': 'form-select'}),
            'card_image_quality': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '100'}),
            'enable_qr_codes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_email_delivery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_bulk_operations': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'enable_api_access': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_expire_cards': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cleanup_old_verifications_days': forms.NumberInput(attrs={'class': 'form-control'}),
        }


# ============================================================================
# REPORTING AND ANALYTICS FORMS
# ============================================================================

class CardReportForm(forms.Form):
    """
    Form for generating card analytics and reports.
    
    Used by admins to create custom reports on card usage and statistics.
    """
    
    REPORT_TYPES = [
        ('summary', 'Summary Report'),
        ('detailed', 'Detailed Card List'),
        ('verifications', 'Verification Activity'),
        ('deliveries', 'Delivery Status'),
        ('expiry', 'Expiry Report'),
    ]
    
    report_type = forms.ChoiceField(
        choices=REPORT_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the type of report to generate"
    )
    
    # Date range
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Start date for report data"
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="End date for report data"
    )
    
    # Filters
    council = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by specific council"
    )
    
    affiliation_type = forms.ChoiceField(
        choices=[
            ('', 'All Types'),
            ('associated', 'Associated'),
            ('designated', 'Designated'),
            ('student', 'Student'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by affiliation type"
    )
    
    status = forms.ChoiceField(
        choices=[
            ('', 'All Statuses'),
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('suspended', 'Suspended'),
            ('revoked', 'Revoked'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Filter by card status"
    )
    
    # Output format
    output_format = forms.ChoiceField(
        choices=[
            ('html', 'HTML View'),
            ('pdf', 'PDF Document'),
            ('csv', 'CSV Export'),
            ('excel', 'Excel Spreadsheet'),
        ],
        initial='html',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Choose output format for the report"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate council choices dynamically
        from enrollments.models import Council
        council_choices = [('', 'All Councils')]
        council_choices.extend([
            (council.code, f"{council.code} - {council.name}")
            for council in Council.objects.filter(is_active=True)
        ])
        self.fields['council'].choices = council_choices
        
        # Set default date range (last 30 days)
        if not self.data:
            self.fields['date_to'].initial = timezone.now().date()
            self.fields['date_from'].initial = timezone.now().date() - timedelta(days=30)
    
    def clean(self):
        """Validate date range."""
        cleaned_data = super().clean()
        
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to:
            if date_from > date_to:
                raise ValidationError("Start date must be before end date")
            
            # Limit report range to prevent performance issues
            if (date_to - date_from).days > 365:
                raise ValidationError("Report date range cannot exceed 365 days")
        
        return cleaned_data


# ============================================================================
# UTILITY FORMS
# ============================================================================

class ContactForm(forms.Form):
    """
    Contact form for card-related inquiries.
    
    Provides a way for affiliates to contact support about their cards.
    """
    
    INQUIRY_TYPES = [
        ('card_issue', 'Card Not Working'),
        ('card_lost', 'Lost or Stolen Card'),
        ('card_renewal', 'Card Renewal'),
        ('technical_issue', 'Technical Problem'),
        ('general_inquiry', 'General Inquiry'),
    ]
    
    inquiry_type = forms.ChoiceField(
        choices=INQUIRY_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="What type of inquiry is this?"
    )
    
    card_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your card number (if applicable)'
        }),
        help_text="Your card number (if you have one)"
    )
    
    contact_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your full name'
        }),
        help_text="Your full name"
    )
    
    contact_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your.email@example.com'
        }),
        help_text="Your email address for our response"
    )
    
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Brief description of your inquiry'
        }),
        help_text="Brief subject line for your inquiry"
    )
    
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 6,
            'placeholder': 'Please provide detailed information about your inquiry...'
        }),
        help_text="Detailed description of your inquiry or issue"
    )
    
    # Optional file attachment
    attachment = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png'
        }),
        help_text="Optional: Attach a relevant file (PDF, Word, or image)"
    )
    
    def clean_attachment(self):
        """Validate attachment file."""
        attachment = self.cleaned_data.get('attachment')
        
        if attachment:
            # Validate file size (2MB max)
            if attachment.size > 2 * 1024 * 1024:
                raise ValidationError("Attachment file size cannot exceed 2MB")
            
            # Validate file type
            allowed_types = [
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'image/jpeg',
                'image/png'
            ]
            
            if attachment.content_type not in allowed_types:
                raise ValidationError("File type not allowed. Please upload PDF, Word, or image files only.")
        
        return attachment