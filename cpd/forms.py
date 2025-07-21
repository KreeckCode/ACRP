"""
CPD Tracking System Forms

Comprehensive form collection supporting all user workflows:
- Admin system management forms
- User activity submission and participation forms  
- Approval workflow forms
- Search and filtering forms

Author: Senior Django Developer
Architecture: Role-based, validation-rich, user-friendly forms
"""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django.db.models import Q
from datetime import datetime, timedelta
from decimal import Decimal

from .models import (
    CPDProvider, CPDCategory, CPDRequirement, CPDActivity, 
    CPDPeriod, CPDRecord, CPDEvidence, CPDApproval, CPDCompliance
)

User = get_user_model()


# ============================================================================
# BASE FORM CLASSES - Reusable components
# ============================================================================

class BaseModelForm(forms.ModelForm):
    """Base form with consistent styling and validation."""
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Apply consistent styling to all form fields
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.URLInput)):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': field.label or field_name.replace('_', ' ').title()
                })
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': f'Enter {field.label or field_name.replace("_", " ").lower()}...'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({'class': 'form-control', 'step': '0.01'})
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'type': 'date'
                })
            elif isinstance(field.widget, forms.DateTimeInput):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'type': 'datetime-local'
                })
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs.update({
                    'class': 'form-control',
                    'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png'
                })
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})


class DateRangeForm(forms.Form):
    """Reusable date range filter form."""
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise ValidationError("Start date cannot be after end date.")
        
        return cleaned_data


# ============================================================================
# ADMIN SYSTEM MANAGEMENT FORMS - For system configuration
# ============================================================================

class CPDProviderForm(BaseModelForm):
    """Form for creating and editing CPD providers."""
    
    class Meta:
        model = CPDProvider
        fields = [
            'name', 'description', 'provider_type', 'website', 
            'contact_email', 'contact_phone', 'is_accredited',
            'accreditation_body', 'quality_rating', 'is_active'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'quality_rating': forms.NumberInput(attrs={'min': 0, 'max': 5, 'step': 0.1}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Conditional field requirements
        self.fields['accreditation_body'].widget.attrs['data-depends'] = 'is_accredited'
        
        # Help text for quality rating
        self.fields['quality_rating'].help_text = "Provider quality rating (0-5 stars)"
    
    def clean(self):
        cleaned_data = super().clean()
        is_accredited = cleaned_data.get('is_accredited')
        accreditation_body = cleaned_data.get('accreditation_body')
        
        if is_accredited and not accreditation_body:
            raise ValidationError({
                'accreditation_body': 'Accreditation body is required for accredited providers.'
            })
        
        return cleaned_data


class CPDCategoryForm(BaseModelForm):
    """Form for creating and editing CPD categories."""
    
    class Meta:
        model = CPDCategory
        fields = [
            'name', 'description', 'short_code', 'points_per_hour',
            'min_hours_per_activity', 'max_hours_per_activity',
            'requires_evidence', 'evidence_description',
            'requires_approval', 'auto_approve_threshold',
            'accredited_multiplier', 'is_active', 'display_order'
        ]
        widgets = {
            'points_per_hour': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
            'min_hours_per_activity': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
            'max_hours_per_activity': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
            'auto_approve_threshold': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
            'accredited_multiplier': forms.NumberInput(attrs={'min': 0.5, 'max': 3.0, 'step': 0.1}),
            'display_order': forms.NumberInput(attrs={'min': 0}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Conditional field display
        self.fields['evidence_description'].widget.attrs['data-depends'] = 'requires_evidence'
        self.fields['auto_approve_threshold'].widget.attrs['data-depends'] = 'requires_approval'
        
        # Field grouping for better UX
        self.fieldsets = [
            ('Basic Information', ['name', 'description', 'short_code']),
            ('Point Calculation', ['points_per_hour', 'accredited_multiplier']),
            ('Activity Constraints', ['min_hours_per_activity', 'max_hours_per_activity']),
            ('Workflow Settings', ['requires_evidence', 'evidence_description', 'requires_approval', 'auto_approve_threshold']),
            ('Display Settings', ['is_active', 'display_order'])
        ]
    
    def clean(self):
        cleaned_data = super().clean()
        min_hours = cleaned_data.get('min_hours_per_activity')
        max_hours = cleaned_data.get('max_hours_per_activity')
        
        if min_hours and max_hours and min_hours > max_hours:
            raise ValidationError({
                'max_hours_per_activity': 'Maximum hours cannot be less than minimum hours.'
            })
        
        return cleaned_data


class CPDRequirementForm(BaseModelForm):
    """Form for creating and editing CPD requirements."""
    
    # Custom field for category requirements
    category_requirements_display = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    class Meta:
        model = CPDRequirement
        fields = [
            'name', 'description', 'council', 'user_level',
            'total_points_required', 'total_hours_required',
            'carry_over_allowed', 'carry_over_max_percentage',
            'effective_date', 'expiry_date', 'is_active'
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'total_points_required': forms.NumberInput(attrs={'min': 0, 'step': 0.5}),
            'total_hours_required': forms.NumberInput(attrs={'min': 0, 'step': 0.5}),
            'carry_over_max_percentage': forms.NumberInput(attrs={'min': 0, 'max': 100, 'step': 1}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add JavaScript for category requirements builder
        self.fields['description'].widget.attrs['data-category-builder'] = 'true'
        
        # Conditional fields
        self.fields['carry_over_max_percentage'].widget.attrs['data-depends'] = 'carry_over_allowed'


class CPDPeriodForm(BaseModelForm):
    """Form for creating and editing CPD periods."""
    
    class Meta:
        model = CPDPeriod
        fields = [
            'name', 'start_date', 'end_date', 'submission_deadline',
            'grace_period_days', 'is_current'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'submission_deadline': forms.DateInput(attrs={'type': 'date'}),
            'grace_period_days': forms.NumberInput(attrs={'min': 0, 'max': 365}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        submission_deadline = cleaned_data.get('submission_deadline')
        
        if start_date and end_date and start_date >= end_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        if end_date and submission_deadline and submission_deadline < end_date:
            raise ValidationError({
                'submission_deadline': 'Submission deadline should be after the period end date.'
            })
        
        return cleaned_data


# ============================================================================
# ACTIVITY MANAGEMENT FORMS - For CPD activities
# ============================================================================

class CPDActivityForm(BaseModelForm):
    """Comprehensive form for creating and editing CPD activities."""
    
    class Meta:
        model = CPDActivity
        fields = [
            'title', 'description', 'provider', 'category', 'activity_type',
            'start_date', 'end_date', 'duration_hours', 'location', 'is_online',
            'meeting_url', 'registration_required', 'registration_deadline',
            'max_participants', 'registration_fee', 'approval_status',
            'points_awarded', 'learning_objectives', 'prerequisites',
            'materials_provided', 'website_url', 'is_accredited',
            'accreditation_body', 'is_active', 'is_featured'
        ]
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'duration_hours': forms.NumberInput(attrs={'min': 0.25, 'step': 0.25}),
            'max_participants': forms.NumberInput(attrs={'min': 1}),
            'registration_fee': forms.NumberInput(attrs={'min': 0, 'step': 0.01}),
            'points_awarded': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
            'learning_objectives': forms.Textarea(attrs={'rows': 4}),
            'prerequisites': forms.Textarea(attrs={'rows': 3}),
            'materials_provided': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Conditional field display based on other fields
        conditional_fields = {
            'meeting_url': 'is_online',
            'registration_deadline': 'registration_required',
            'max_participants': 'registration_required',
            'registration_fee': 'registration_required',
            'accreditation_body': 'is_accredited',
        }
        
        for field, depends_on in conditional_fields.items():
            self.fields[field].widget.attrs['data-depends'] = depends_on
        
        # Auto-calculate points based on category and duration
        self.fields['points_awarded'].help_text = "Leave blank to auto-calculate based on category"
        
        # Provider filtering for non-admins
        if self.user and not self.user.is_staff:
            self.fields['provider'].queryset = CPDProvider.objects.filter(
                Q(provider_type=CPDProvider.ProviderType.EXTERNAL) |
                Q(created_by=self.user)
            )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        registration_required = cleaned_data.get('registration_required')
        registration_deadline = cleaned_data.get('registration_deadline')
        is_online = cleaned_data.get('is_online')
        meeting_url = cleaned_data.get('meeting_url')
        
        # Date validation
        if start_date and end_date and start_date > end_date:
            raise ValidationError({
                'end_date': 'End date cannot be before start date.'
            })
        
        # Registration validation
        if registration_required and not registration_deadline:
            raise ValidationError({
                'registration_deadline': 'Registration deadline is required when registration is required.'
            })
        
        # Online meeting validation
        if is_online and not meeting_url:
            raise ValidationError({
                'meeting_url': 'Meeting URL is required for online activities.'
            })
        
        return cleaned_data


class UserCPDActivityForm(BaseModelForm):
    """Simplified form for users to submit external CPD activities."""
    
    class Meta:
        model = CPDActivity
        fields = [
            'title', 'description', 'category', 'activity_type',
            'start_date', 'end_date', 'duration_hours', 'location',
            'learning_objectives', 'website_url'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'duration_hours': forms.NumberInput(attrs={'min': 0.25, 'step': 0.25}),
            'learning_objectives': forms.Textarea(attrs={'rows': 4}),
        }
    
    # Custom fields for external provider
    provider_name = forms.CharField(
        max_length=200,
        label="Provider/Organization",
        help_text="Name of the organization providing this activity"
    )
    provider_website = forms.URLField(
        required=False,
        label="Provider Website",
        help_text="Website of the provider (if available)"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit categories to those that allow user submissions
        self.fields['category'].queryset = CPDCategory.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')
        
        # Add help text
        self.fields['title'].help_text = "Full title of the CPD activity"
        self.fields['description'].help_text = "Detailed description of what was covered"
        self.fields['duration_hours'].help_text = "Total hours of participation"
    
    def save(self, commit=True):
        """Create or get provider and save activity."""
        instance = super().save(commit=False)
        
        # Get or create external provider
        provider_name = self.cleaned_data['provider_name']
        provider_website = self.cleaned_data.get('provider_website')
        
        provider, created = CPDProvider.objects.get_or_create(
            name=provider_name,
            defaults={
                'provider_type': CPDProvider.ProviderType.EXTERNAL,
                'website': provider_website,
                'created_by': self.user
            }
        )
        
        instance.provider = provider
        instance.approval_status = CPDActivity.ApprovalStatus.REQUIRES_APPROVAL
        instance.created_by = self.user
        
        if commit:
            instance.save()
        
        return instance


# ============================================================================
# USER PARTICIPATION FORMS - For user CPD records
# ============================================================================

class CPDRecordForm(BaseModelForm):
    """Form for users to register for or record CPD activities."""
    
    class Meta:
        model = CPDRecord
        fields = [
            'activity', 'attendance_date', 'completion_date',
            'hours_claimed', 'user_rating', 'user_feedback',
            'would_recommend', 'notes'
        ]
        widgets = {
            'attendance_date': forms.DateInput(attrs={'type': 'date'}),
            'completion_date': forms.DateInput(attrs={'type': 'date'}),
            'hours_claimed': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
            'user_rating': forms.Select(choices=[(i, f"{i} Star{'s' if i > 1 else ''}") for i in range(1, 6)]),
            'user_feedback': forms.Textarea(attrs={'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        self.activity = kwargs.pop('activity', None)
        super().__init__(*args, **kwargs)
        
        if self.activity:
            # Pre-populate activity if provided
            self.fields['activity'].initial = self.activity
            self.fields['activity'].widget = forms.HiddenInput()
            
            # Set default hours from activity
            self.fields['hours_claimed'].initial = self.activity.duration_hours
        
        # Make completion date dependent on attendance date
        self.fields['completion_date'].widget.attrs['data-depends'] = 'attendance_date'
        
        # Add help text
        self.fields['hours_claimed'].help_text = "Hours you actually participated (may differ from scheduled hours)"
        self.fields['user_feedback'].help_text = "Share your experience to help improve future activities"
    
    def clean(self):
        cleaned_data = super().clean()
        attendance_date = cleaned_data.get('attendance_date')
        completion_date = cleaned_data.get('completion_date')
        
        if attendance_date and completion_date and attendance_date > completion_date:
            raise ValidationError({
                'completion_date': 'Completion date cannot be before attendance date.'
            })
        
        return cleaned_data


class CPDEvidenceForm(BaseModelForm):
    """Form for uploading CPD evidence files."""
    
    class Meta:
        model = CPDEvidence
        fields = ['file', 'evidence_type', 'description']
        widgets = {
            'file': forms.FileInput(attrs={
                'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png',
                'class': 'form-control'
            }),
            'description': forms.TextInput(attrs={
                'placeholder': 'Brief description of this document...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add file size validation help text
        self.fields['file'].help_text = "Upload supporting documents (PDF, DOC, JPG, PNG). Max size: 10MB"
        
        # Dynamic help text based on evidence type
        evidence_help = {
            'CERTIFICATE': 'Upload your completion certificate',
            'ATTENDANCE': 'Upload attendance record or confirmation',
            'TRANSCRIPT': 'Upload academic transcript',
            'RECEIPT': 'Upload payment receipt',
            'AGENDA': 'Upload event agenda or program',
            'REFLECTION': 'Upload learning reflection document',
        }
        
        self.fields['evidence_type'].help_text = "Select the type of evidence you're uploading"
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        
        if file:
            # Check file size (10MB limit)
            if file.size > 10 * 1024 * 1024:
                raise ValidationError("File size cannot exceed 10MB.")
            
            # Check file type
            allowed_types = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
            file_extension = file.name.lower().split('.')[-1]
            if f'.{file_extension}' not in allowed_types:
                raise ValidationError(f"File type .{file_extension} not allowed. Use: {', '.join(allowed_types)}")
        
        return file


# ============================================================================
# ADMIN WORKFLOW FORMS - For approval and management
# ============================================================================

class CPDApprovalForm(BaseModelForm):
    """Form for admin to approve/reject CPD records."""
    
    class Meta:
        model = CPDApproval
        fields = [
            'status', 'reviewer_comments', 'rejection_reason',
            'adjusted_points', 'adjustment_reason', 'priority'
        ]
        widgets = {
            'reviewer_comments': forms.Textarea(attrs={'rows': 4}),
            'rejection_reason': forms.Textarea(attrs={'rows': 3}),
            'adjustment_reason': forms.Textarea(attrs={'rows': 3}),
            'adjusted_points': forms.NumberInput(attrs={'min': 0, 'step': 0.25}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Conditional field display
        self.fields['rejection_reason'].widget.attrs['data-depends'] = 'status'
        self.fields['adjusted_points'].widget.attrs['data-depends'] = 'status'
        self.fields['adjustment_reason'].widget.attrs['data-depends'] = 'adjusted_points'
        
        # Show original points for reference
        if self.instance and self.instance.pk:
            self.fields['adjusted_points'].help_text = f"Original points claimed: {self.instance.original_points}"
    
    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        rejection_reason = cleaned_data.get('rejection_reason')
        adjusted_points = cleaned_data.get('adjusted_points')
        adjustment_reason = cleaned_data.get('adjustment_reason')
        
        # Require rejection reason for rejected status
        if status == CPDApproval.Status.REJECTED and not rejection_reason:
            raise ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting an application.'
            })
        
        # Require adjustment reason if points are adjusted
        if adjusted_points and adjusted_points != self.instance.original_points:
            if not adjustment_reason:
                raise ValidationError({
                    'adjustment_reason': 'Please explain why points were adjusted.'
                })
        
        return cleaned_data


class BulkApprovalForm(forms.Form):
    """Form for bulk approval operations."""
    
    action = forms.ChoiceField(
        choices=[
            ('approve', 'Approve Selected'),
            ('reject', 'Reject Selected'),
            ('priority_high', 'Set Priority to High'),
            ('priority_normal', 'Set Priority to Normal'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    selected_records = forms.CharField(
        widget=forms.HiddenInput(),
        help_text="Comma-separated list of record IDs"
    )
    
    bulk_comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional comments for all selected records...'}),
        label="Bulk Comments"
    )
    
    def clean_selected_records(self):
        """Validate that selected records exist and are in pending status."""
        selected = self.cleaned_data['selected_records']
        
        try:
            record_ids = [int(id.strip()) for id in selected.split(',') if id.strip()]
        except ValueError:
            raise ValidationError("Invalid record IDs provided.")
        
        if not record_ids:
            raise ValidationError("No records selected.")
        
        # Verify records exist and are in correct status
        pending_count = CPDApproval.objects.filter(
            id__in=record_ids,
            status__in=[CPDApproval.Status.PENDING, CPDApproval.Status.UNDER_REVIEW]
        ).count()
        
        if pending_count != len(record_ids):
            raise ValidationError("Some selected records are not available for bulk operations.")
        
        return record_ids


# ============================================================================
# SEARCH AND FILTER FORMS - For data discovery
# ============================================================================

class CPDActivitySearchForm(forms.Form):
    """Comprehensive search form for CPD activities."""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search activities, providers, or descriptions...',
            'class': 'form-control'
        })
    )
    
    category = forms.ModelChoiceField(
        queryset=CPDCategory.objects.filter(is_active=True),
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    provider = forms.ModelChoiceField(
        queryset=CPDProvider.objects.filter(is_active=True),
        required=False,
        empty_label="All Providers",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    activity_type = forms.ChoiceField(
        choices=[('', 'All Types')] + CPDActivity.ActivityType.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    approval_status = forms.ChoiceField(
        choices=[('', 'All Status')] + CPDActivity.ApprovalStatus.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    is_online = forms.ChoiceField(
        choices=[('', 'All Formats'), ('true', 'Online Only'), ('false', 'In-Person Only')],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    registration_open = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Registration Open Only"
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Limit provider choices for non-staff users
        if self.user and not self.user.is_staff:
            self.fields['provider'].queryset = CPDProvider.objects.filter(
                Q(provider_type=CPDProvider.ProviderType.EXTERNAL) |
                Q(provider_type=CPDProvider.ProviderType.ACCREDITED)
            )


class CPDRecordFilterForm(forms.Form):
    """Filter form for CPD records dashboard."""
    
    period = forms.ModelChoiceField(
        queryset=CPDPeriod.objects.all(),
        required=False,
        empty_label="All Periods",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + CPDRecord.Status.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    category = forms.ModelChoiceField(
        queryset=CPDCategory.objects.filter(is_active=True),
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    approval_status = forms.ChoiceField(
        choices=[('', 'All Approval Status')] + CPDApproval.Status.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    points_min = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min points'})
    )
    
    points_max = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max points'})
    )


class ComplianceReportForm(forms.Form):
    """Form for generating compliance reports."""
    
    period = forms.ModelChoiceField(
        queryset=CPDPeriod.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    council = forms.ChoiceField(
        choices=[('ALL', 'All Councils')] + CPDRequirement.Council.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    user_level = forms.ChoiceField(
        choices=[('ALL', 'All Levels')] + CPDRequirement.UserLevel.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    compliance_status = forms.MultipleChoiceField(
        choices=CPDCompliance.Status.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )
    
    report_format = forms.ChoiceField(
        choices=[
            ('html', 'Web Report'),
            ('pdf', 'PDF Report'),
            ('excel', 'Excel Spreadsheet'),
            ('csv', 'CSV Data'),
        ],
        initial='html',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    include_details = forms.BooleanField(
        required=False,
        initial=True,
        label="Include Activity Details",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    include_evidence = forms.BooleanField(
        required=False,
        label="Include Evidence Summary",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


# ============================================================================
# WIZARD FORMS - Multi-step processes
# ============================================================================

class CPDSubmissionWizardForm1(forms.Form):
    """Step 1: Activity Selection or Creation"""
    
    submission_type = forms.ChoiceField(
        choices=[
            ('existing', 'Register for Existing Activity'),
            ('external', 'Submit External Activity'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label="How would you like to record your CPD?"
    )
    
    existing_activity = forms.ModelChoiceField(
        queryset=CPDActivity.objects.filter(
            approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED,
            is_active=True
        ),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        submission_type = cleaned_data.get('submission_type')
        existing_activity = cleaned_data.get('existing_activity')
        
        if submission_type == 'existing' and not existing_activity:
            raise ValidationError({
                'existing_activity': 'Please select an activity to register for.'
            })
        
        return cleaned_data


class CPDSubmissionWizardForm2(UserCPDActivityForm):
    """Step 2: External Activity Details (if applicable)"""
    pass


class CPDSubmissionWizardForm3(CPDRecordForm):
    """Step 3: Participation Details"""
    pass


class CPDSubmissionWizardForm4(CPDEvidenceForm):
    """Step 4: Evidence Upload"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make evidence optional for some categories
        self.fields['file'].required = False
        self.fields['file'].help_text = "Upload supporting evidence if available. You can add more evidence later."


# ============================================================================
# QUICK ACTION FORMS - For common operations
# ============================================================================

class QuickRegistrationForm(forms.Form):
    """Quick registration form for pre-approved activities."""
    
    activity = forms.ModelChoiceField(
        queryset=CPDActivity.objects.filter(
            approval_status=CPDActivity.ApprovalStatus.PRE_APPROVED,
            is_active=True
        ),
        widget=forms.HiddenInput()
    )
    
    agree_terms = forms.BooleanField(
        label="I agree to attend this activity and understand the CPD requirements",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Any special requirements or notes...'}),
        label="Additional Notes"
    )


class QuickFeedbackForm(forms.ModelForm):
    """Quick feedback form for completed activities."""
    
    class Meta:
        model = CPDRecord
        fields = ['user_rating', 'user_feedback', 'would_recommend']
        widgets = {
            'user_rating': forms.Select(
                choices=[(i, f"⭐" * i) for i in range(1, 6)],
                attrs={'class': 'form-select'}
            ),
            'user_feedback': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Share your experience with this activity...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user_rating'].label = "Overall Rating"
        self.fields['user_feedback'].label = "Your Feedback"
        self.fields['would_recommend'].label = "Would you recommend this activity to others?"


# ============================================================================
# FORM FACTORY FUNCTIONS - Dynamic form creation
# ============================================================================

def get_activity_form_for_user(user, activity=None):
    """Get appropriate activity form based on user permissions."""
    
    if user.is_staff or user.acrp_role in ['PROVIDER_ADMIN', 'INTERNAL_FACILITATOR']:
        return CPDActivityForm
    else:
        return UserCPDActivityForm


def get_record_form_for_status(record_status):
    """Get appropriate record form based on current status."""
    
    if record_status in [CPDRecord.Status.REGISTERED]:
        return CPDRecordForm
    elif record_status in [CPDRecord.Status.COMPLETED]:
        return QuickFeedbackForm
    else:
        return CPDRecordForm


def create_category_requirement_form(requirement):
    """Dynamically create form for category-specific requirements."""
    
    class CategoryRequirementForm(forms.Form):
        pass
    
    # Add fields for each active category
    for category in CPDCategory.objects.filter(is_active=True):
        field_name_points = f"category_{category.id}_min_points"
        field_name_hours = f"category_{category.id}_min_hours"
        
        setattr(CategoryRequirementForm, field_name_points, forms.DecimalField(
            required=False,
            min_value=0,
            label=f"{category.name} - Min Points",
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'})
        ))
        
        setattr(CategoryRequirementForm, field_name_hours, forms.DecimalField(
            required=False,
            min_value=0,
            label=f"{category.name} - Min Hours",
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'})
        ))
    
    return CategoryRequirementForm