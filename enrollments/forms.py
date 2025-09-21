import os
from django import forms
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory

from .models import (
    # Core models
    Council,
    AffiliationType,
    DesignationCategory,
    DesignationSubcategory,
    OnboardingSession,
    
    # Application models
    BaseApplication,
    AssociatedApplication,
    DesignatedApplication,
    StudentApplication,
    
    # Related models
    AcademicQualification,
    Reference,
    PracticalExperience,
    Document,
)

# ============================================================================
# ENHANCED STYLING WIDGETS - Consistent across all forms
# ============================================================================

DATE_WIDGET = forms.DateInput(attrs={
    "type": "date", 
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
})

TEXTAREA_WIDGET = forms.Textarea(attrs={
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
    "rows": 4,
})

TEXT_INPUT_WIDGET = forms.TextInput(attrs={
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
})

EMAIL_WIDGET = forms.EmailInput(attrs={
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
    "placeholder": "your.email@example.com"
})

SELECT_WIDGET = forms.Select(attrs={
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
})

CHECKBOX_WIDGET = forms.CheckboxInput(attrs={
    "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
})

RADIO_WIDGET = forms.RadioSelect(attrs={
    "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
})


# ============================================================================
# MULTIPLE FILE UPLOAD COMPONENTS
# ============================================================================

class MultipleFileInput(forms.ClearableFileInput):
    """Enhanced multiple file input widget"""
    allow_multiple_selected = True
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors',
            'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png,.gif',
            'multiple': True
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class MultipleFileField(forms.FileField):
    """Enhanced multiple file field with comprehensive validation"""
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)
    
    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data if d]
        else:
            result = [single_file_clean(data, initial)] if data else []
        return result


# ============================================================================
# ONBOARDING FLOW FORMS - Guide users through selection process
# ============================================================================
class AffiliationTypeSelectionForm(forms.Form):
    """
    First step: User selects their affiliation type.
    """
    AFFILIATION_CHOICES = [
        ('associated', 'Associated Affiliation'),
        ('designated', 'Designated Affiliation'), 
        ('student', 'Student Affiliation'),
    ]
    
    affiliation_type = forms.ChoiceField(
        choices=AFFILIATION_CHOICES,
        widget=forms.RadioSelect(attrs={
            "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
        }),
        required=True,
        help_text="Choose the type of affiliation you want to apply for"
    )

class CouncilSelectionForm(forms.Form):
    """
    Second step: User selects which council they want to join.
    All affiliation types need to select a council.
    """
    council = forms.ModelChoiceField(
        queryset=Council.objects.filter(is_active=True),
        widget=forms.RadioSelect(attrs={
            "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
        }),
        empty_label=None,
        required=True,
        help_text="Choose the council that best matches your ministry focus"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Customize labels with descriptions
        choices = []
        for council in self.fields['council'].queryset:
            label = f"{council.code} - {council.name}"
            if council.description:
                desc = council.description[:100] + "..." if len(council.description) > 100 else council.description
                label += f" ({desc})"
            choices.append((council.pk, label))
        
        self.fields['council'].choices = choices

class DesignationCategorySelectionForm(forms.Form):
    """
    Third step (for designated affiliations): Select designation category.
    
    Only shown for designated affiliation type.
    """
    designation_category = forms.ModelChoiceField(
        queryset=DesignationCategory.objects.filter(is_active=True),
        widget=forms.RadioSelect(attrs={
            "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
        }),
        empty_label=None,
        required=True,
        help_text="Choose your level of professional designation"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Order by level and customize labels
        choices = []
        for category in self.fields['designation_category'].queryset.order_by('level'):
            label = f"Level {category.level}: {category.name}"
            if category.description:
                label += f" - {category.description}"
            choices.append((category.pk, label))
        
        self.fields['designation_category'].choices = choices


class DesignationSubcategorySelectionForm(forms.Form):
    """
    Fourth step (for CPSC designated affiliations): Select subcategory.
    
    Only shown for CPSC council with designated affiliation.
    """
    designation_subcategory = forms.ModelChoiceField(
        queryset=DesignationSubcategory.objects.none(),  # Will be populated dynamically
        widget=forms.RadioSelect(attrs={
            "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
        }),
        empty_label=None,
        required=True,
        help_text="Choose your specific area of specialization"
    )
    
    def __init__(self, category=None, council=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if category and council:
            # Filter subcategories by selected category and council
            self.fields['designation_subcategory'].queryset = DesignationSubcategory.objects.filter(
                category=category,
                council=council,
                is_active=True
            )
            
            # Customize labels
            choices = []
            for subcategory in self.fields['designation_subcategory'].queryset:
                label = subcategory.name
                if subcategory.description:
                    label += f" - {subcategory.description}"
                choices.append((subcategory.pk, label))
            
            self.fields['designation_subcategory'].choices = choices


class OnboardingSessionForm(forms.ModelForm):
    """
    Form for creating/updating onboarding sessions.
    
    This is mainly used internally to track user progress.
    """
    class Meta:
        model = OnboardingSession
        fields = [
            'selected_affiliation_type',
            'selected_council', 
        ]
        widgets = {
            'selected_affiliation_type': SELECT_WIDGET,
            'selected_council': SELECT_WIDGET,
        }
    
    def clean(self):
        """Validate onboarding session choices - SIMPLIFIED"""
        cleaned_data = super().clean()
        
        
        affiliation_type = cleaned_data.get('selected_affiliation_type')
        council = cleaned_data.get('selected_council')
        
        # Simple validation - just need affiliation type and council
        if not affiliation_type:
            raise ValidationError({'selected_affiliation_type': 'Affiliation type is required'})
        if not council:
            raise ValidationError({'selected_council': 'Council selection is required'})
        
        return cleaned_data


# ============================================================================
# BASE APPLICATION FORM - Common fields and functionality
# ============================================================================

class BaseApplicationForm(forms.ModelForm):
    """
    Base form for all application types.
    
    Contains all common fields from BaseApplication model and shared
    validation logic. Specific application forms inherit from this.
    """
    
    def __init__(self, *args, request=None, onboarding_session=None, **kwargs):
        """
        Enhanced initialization with request and onboarding session context.
        
        Args:
            request: HTTP request object for user context
            onboarding_session: OnboardingSession instance for this application
        """
        self.request = request
        self.onboarding_session = onboarding_session
        super().__init__(*args, **kwargs)
        
        # Apply consistent styling to all fields
        self._apply_field_styling()
        
        # Set required field indicators
        self._mark_required_fields()
        
        # Add help text for complex fields
        self._add_field_help_text()
    
    def _apply_field_styling(self):
        """Apply consistent CSS classes to all form fields"""
        for field_name, field in self.fields.items():
            widget_class = field.widget.__class__
            
            if widget_class in [forms.TextInput, forms.EmailInput]:
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })
            elif widget_class == forms.Textarea:
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                    "rows": 4
                })
            elif widget_class == forms.Select:
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })
            elif widget_class == forms.CheckboxInput:
                field.widget.attrs.update({
                    "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                })
            elif widget_class == forms.DateInput:
                field.widget.attrs.update({
                    "type": "date",
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })
    
    def _mark_required_fields(self):
        """Add asterisk to required field labels"""
        for field_name, field in self.fields.items():
            if field.required and field.label:
                field.label = f"{field.label} *"
                field.widget.attrs.update({"required": True})
    
    def _add_field_help_text(self):
        """Add helpful descriptions to complex fields"""
        help_texts = {
            'id_number': 'Enter your 13-digit South African ID number',
            'passport_number': 'Required for non-SA citizens or dual nationality',
            'disability': 'Specify any disabilities or special accommodations needed',
            'physical_same_as_postal': 'Check if your physical address is the same as postal',
            'religious_affiliation': 'Optional: Your denomination or religious organization',
            'other_languages': 'List additional languages you speak (comma-separated)',
            'years_in_ministry': 'Total years of experience in ministry or related work',
            'disciplinary_action': 'Have you ever been subject to disciplinary action by any professional body?',
            'actively_involved_pastoral_counselling': 'Are you currently providing pastoral counselling services?',
        }
        
        for field_name, help_text in help_texts.items():
            if field_name in self.fields and not self.fields[field_name].help_text:
                self.fields[field_name].help_text = help_text
    
    def clean_email(self):
        """Validate email uniqueness across all application types"""
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower().strip()
            
            # Check against all application types
            from django.contrib.contenttypes.models import ContentType
            
            for app_model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
                existing_query = app_model.objects.filter(email__iexact=email)
                if self.instance and self.instance.pk:
                    existing_query = existing_query.exclude(pk=self.instance.pk)
                
                if existing_query.exists():
                    raise ValidationError("This email address is already registered.")
        
        return email
    
    def clean_id_number(self):
        """Validate ID number format and uniqueness"""
        id_number = self.cleaned_data.get("id_number")
        if id_number:
            # Sanitize ID number
            id_number = id_number.replace(" ", "").replace("-", "")
            
            # Validate format
            if not id_number.isdigit() or len(id_number) != 13:
                raise ValidationError("Please enter a valid 13-digit South African ID number.")
            
            # Check uniqueness across all application types
            for app_model in [AssociatedApplication, DesignatedApplication, StudentApplication]:
                existing_query = app_model.objects.filter(id_number=id_number)
                if self.instance and self.instance.pk:
                    existing_query = existing_query.exclude(pk=self.instance.pk)
                
                if existing_query.exists():
                    raise ValidationError("This ID number is already registered.")
        
        return id_number
    
    def clean_date_of_birth(self):
        """Validate age requirements"""
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = timezone.now().date()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
            elif age < 16:
                raise ValidationError("Applicant must be at least 16 years old.")
            elif age > 100:
                raise ValidationError("Please verify the date of birth.")
        
        return dob
    
    def clean(self):
        """Cross-field validation common to all applications"""
        cleaned_data = super().clean()
        
        # Validate disciplinary action details
        if cleaned_data.get("disciplinary_action") and not cleaned_data.get("disciplinary_description"):
            raise ValidationError({
                "disciplinary_description": "Please provide details about the disciplinary action."
            })
        
        # Validate physical address fields if different from postal
        if not cleaned_data.get("physical_same_as_postal"):
            required_physical_fields = [
                'physical_address_line1', 'physical_city', 
                'physical_province', 'physical_code'
            ]
            for field in required_physical_fields:
                if not cleaned_data.get(field):
                    raise ValidationError({
                        field: "This field is required when physical address differs from postal address."
                    })
        
        # Validate legal agreements
        required_agreements = [
            ('popi_act_accepted', 'POPIA consent'),
            ('terms_accepted', 'Terms and conditions'),
            ('information_accurate', 'Information accuracy certification'),
            ('declaration_accepted', 'Professional declaration')
        ]
        
        for field, description in required_agreements:
            if not cleaned_data.get(field):
                raise ValidationError({
                    field: f"You must accept {description} to continue."
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Enhanced save with onboarding session linking"""
        instance = super().save(commit=False)
        
        # Link to onboarding session if provided
        if self.onboarding_session:
            instance.onboarding_session = self.onboarding_session
        
        # Set the submitting user if available
        if self.request and hasattr(self.request, 'user'):
            if not instance.pk:  # New instance
                instance._submitted_by = self.request.user
        
        if commit:
            instance.save()
        
        return instance
    
    class Meta:
        model = BaseApplication
        fields = [
            # Personal Information
            'title', 'gender', 'surname', 'initials', 'full_names', 'preferred_name',
            'id_number', 'passport_number', 'date_of_birth', 'race', 'disability', 'residency', 'nationality',
            
            # Contact Information
            'email', 'cell_phone', 'work_phone', 'home_phone', 'fax',
            'postal_address_line1', 'postal_address_line2', 'postal_city', 
            'postal_province', 'postal_code', 'postal_country',
            'physical_same_as_postal', 'physical_address_line1', 'physical_address_line2',
            'physical_city', 'physical_province', 'physical_code', 'physical_country',
            
            # Religious and Linguistic Information
            'religious_affiliation', 'home_language', 'other_languages',
            
            # Educational Background
            'highest_qualification', 'qualification_institution', 'qualification_date',

            'ministry_name', 'denomination', 'ministry_type', 'ministry_type_other', 
            
            # Professional Background
            'current_occupation', 'work_description', 'years_in_ministry', 'years_in_part_time_ministry',
            
            # Background Checks
            'disciplinary_action', 'disciplinary_description',
            
            # Pastoral Counselling
            'actively_involved_pastoral_counselling',
            
            # Legal Agreements
            'popi_act_accepted', 'terms_accepted', 'information_accurate', 'declaration_accepted',
        ]
        widgets = {
            'title': SELECT_WIDGET,
            'gender': SELECT_WIDGET,
            'surname': TEXT_INPUT_WIDGET,
            'initials': TEXT_INPUT_WIDGET,
            'full_names': TEXT_INPUT_WIDGET,
            'preferred_name': TEXT_INPUT_WIDGET,
            'id_number': TEXT_INPUT_WIDGET,
            'passport_number': TEXT_INPUT_WIDGET,
            'date_of_birth': DATE_WIDGET,
            'race': SELECT_WIDGET,
            'email': EMAIL_WIDGET,
            'cell_phone': TEXT_INPUT_WIDGET,
            'work_phone': TEXT_INPUT_WIDGET,
            'home_phone': TEXT_INPUT_WIDGET,
            'fax': TEXT_INPUT_WIDGET,
            'postal_address_line1': TEXT_INPUT_WIDGET,
            'postal_address_line2': TEXT_INPUT_WIDGET,
            'postal_city': TEXT_INPUT_WIDGET,
            'postal_province': SELECT_WIDGET,
            'postal_code': TEXT_INPUT_WIDGET,
            'postal_country': TEXT_INPUT_WIDGET,
            'physical_same_as_postal': CHECKBOX_WIDGET,
            'physical_address_line1': TEXT_INPUT_WIDGET,
            'physical_address_line2': TEXT_INPUT_WIDGET,
            'physical_city': TEXT_INPUT_WIDGET,
            'physical_code': TEXT_INPUT_WIDGET,
            'physical_country': TEXT_INPUT_WIDGET,
            'religious_affiliation': TEXT_INPUT_WIDGET,
            'other_languages': TEXT_INPUT_WIDGET,
            'highest_qualification': TEXT_INPUT_WIDGET,
            'qualification_institution': TEXT_INPUT_WIDGET,
            'qualification_date': DATE_WIDGET,
            'current_occupation': TEXT_INPUT_WIDGET,
            'work_description': TEXTAREA_WIDGET,
            'years_in_ministry': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "0", "max": "70"
            }),
            'disciplinary_action': CHECKBOX_WIDGET,
            'disciplinary_description': TEXTAREA_WIDGET,
            'actively_involved_pastoral_counselling': CHECKBOX_WIDGET,
            'popi_act_accepted': CHECKBOX_WIDGET,
            'terms_accepted': CHECKBOX_WIDGET,
            'information_accurate': CHECKBOX_WIDGET,
            'declaration_accepted': CHECKBOX_WIDGET,
        }
        abstract = True


# ============================================================================
# SPECIFIC APPLICATION FORMS
# ============================================================================

class AssociatedApplicationForm(BaseApplicationForm):
    """
    Form for Associated Affiliation applications.
    
    Uses only the base fields - no additional requirements.
    This is the simplest application type.
    """
    
    def __init__(self, *args, **kwargs):
        # Extract onboarding_session before calling super()
        self.onboarding_session = kwargs.pop('onboarding_session', None)
        
        super().__init__(*args, **kwargs)
        
        # CRITICAL FIX: Auto-populate designation fields from onboarding session
        if self.onboarding_session:
            if 'designation_category' in self.fields and self.onboarding_session.selected_designation_category:
                self.fields['designation_category'].initial = self.onboarding_session.selected_designation_category
                self.initial['designation_category'] = self.onboarding_session.selected_designation_category.pk
                
            if 'designation_subcategory' in self.fields and self.onboarding_session.selected_designation_subcategory:
                self.fields['designation_subcategory'].initial = self.onboarding_session.selected_designation_subcategory
                self.initial['designation_subcategory'] = self.onboarding_session.selected_designation_subcategory.pk
        
        # Set some fields as optional
        self.fields['high_school_name'].required = False
        self.fields['high_school_year_completed'].required = False
        self.fields['supervision_period_end'].required = False
        self.fields['other_professional_memberships'].required = False
        
        # CRITICAL: Make designation fields optional since they're set from onboarding session
        if 'designation_category' in self.fields:
            self.fields['designation_category'].required = False
            self.fields['designation_category'].help_text = 'Set during onboarding process'
            
        if 'designation_subcategory' in self.fields:
            self.fields['designation_subcategory'].required = False
            self.fields['designation_subcategory'].help_text = 'Set during onboarding process'
    
    def clean(self):
        """Designated application specific validation"""
        cleaned_data = super().clean()
        
        # CRITICAL: Force designation fields from onboarding session
        if self.onboarding_session:
            if self.onboarding_session.selected_designation_category:
                cleaned_data['designation_category'] = self.onboarding_session.selected_designation_category
            if self.onboarding_session.selected_designation_subcategory:
                cleaned_data['designation_subcategory'] = self.onboarding_session.selected_designation_subcategory
        
        # Validate supervision period
        start_date = cleaned_data.get('supervision_period_start')
        end_date = cleaned_data.get('supervision_period_end')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({
                'supervision_period_end': 'End date must be after start date.'
            })
        
        # Validate high school year
        high_school_year = cleaned_data.get('high_school_year_completed')
        if high_school_year:
            current_year = timezone.now().year
            if high_school_year > current_year:
                raise ValidationError({
                    'high_school_year_completed': 'Year cannot be in the future.'
                })
            elif high_school_year < 1950:
                raise ValidationError({
                    'high_school_year_completed': 'Please verify the year.'
                })
        
        return cleaned_data
    
    class Meta(BaseApplicationForm.Meta):
        model = DesignatedApplication
        fields = BaseApplicationForm.Meta.fields + [
            'designation_category', 'designation_subcategory',
            'high_school_name', 'high_school_year_completed',
            'supervisor_name', 'supervisor_qualification', 'supervisor_email', 
            'supervisor_phone', 'supervisor_address',
            'supervision_hours_received', 'supervision_period_start', 'supervision_period_end',
            'professional_development_plans', 'other_professional_memberships'
        ]
        widgets = {
            **BaseApplicationForm.Meta.widgets,
            'designation_category': SELECT_WIDGET,
            'designation_subcategory': SELECT_WIDGET,
            'high_school_name': TEXT_INPUT_WIDGET,
            'high_school_year_completed': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "1950", "max": str(timezone.now().year)
            }),
            'supervisor_name': TEXT_INPUT_WIDGET,
            'supervisor_qualification': TEXT_INPUT_WIDGET,
            'supervisor_email': EMAIL_WIDGET,
            'supervisor_phone': TEXT_INPUT_WIDGET,
            'supervisor_address': TEXTAREA_WIDGET,
            'supervision_hours_received': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "0"
            }),
            'supervision_period_start': DATE_WIDGET,
            'supervision_period_end': DATE_WIDGET,
            'professional_development_plans': TEXTAREA_WIDGET,
            'other_professional_memberships': TEXTAREA_WIDGET,
        }



class StudentApplicationForm(BaseApplicationForm):
    """
    Form for Student Affiliation applications.
    
    Includes additional student-specific fields.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # CRITICAL FIX: Auto-populate designation fields from onboarding session
        if self.onboarding_session:
            if 'designation_category' in self.fields and self.onboarding_session.selected_designation_category:
                self.fields['designation_category'].initial = self.onboarding_session.selected_designation_category
                self.initial['designation_category'] = self.onboarding_session.selected_designation_category.pk
                
            if 'designation_subcategory' in self.fields and self.onboarding_session.selected_designation_subcategory:
                self.fields['designation_subcategory'].initial = self.onboarding_session.selected_designation_subcategory
                self.initial['designation_subcategory'] = self.onboarding_session.selected_designation_subcategory.pk
        
        # Add student-specific help text
        self.fields['current_institution'].help_text = 'Name of the educational institution where you are currently studying'
        self.fields['course_of_study'].help_text = 'Full name of your current course or program'
        self.fields['expected_graduation'].help_text = 'When do you expect to complete your studies?'
        self.fields['academic_supervisor_name'].help_text = 'Name and title of your academic supervisor'
    
    def clean_expected_graduation(self):
        """Validate that expected graduation is in the future"""
        expected_grad = self.cleaned_data.get('expected_graduation')
        if expected_grad and expected_grad <= timezone.now().date():
            raise ValidationError("Expected graduation date should be in the future.")
        return expected_grad
    
    class Meta(BaseApplicationForm.Meta):
        model = StudentApplication
        fields = BaseApplicationForm.Meta.fields + [
            'current_institution', 'course_of_study', 'expected_graduation',
            'student_number', 'year_of_study',
            'academic_supervisor_name', 'academic_supervisor_email', 'academic_supervisor_phone'
        ]
        widgets = {
            **BaseApplicationForm.Meta.widgets,
            'current_institution': TEXT_INPUT_WIDGET,
            'course_of_study': TEXT_INPUT_WIDGET,
            'expected_graduation': DATE_WIDGET,
            'student_number': TEXT_INPUT_WIDGET,
            'year_of_study': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "1", "max": "10"
            }),
            'academic_supervisor_name': TEXT_INPUT_WIDGET,
            'academic_supervisor_email': EMAIL_WIDGET,
            'academic_supervisor_phone': TEXT_INPUT_WIDGET,
        }


class DesignatedApplicationForm(BaseApplicationForm):
    """
    Form for Designated Affiliation applications.
    
    Most comprehensive form with all professional requirements.
    """
    
    def __init__(self, *args, **kwargs):
        # Extract onboarding_session before calling super()
        self.onboarding_session = kwargs.pop('onboarding_session', None)
        
        super().__init__(*args, **kwargs)
        
        # CRITICAL FIX: Auto-populate designation fields from onboarding session
        if self.onboarding_session:
            if 'designation_category' in self.fields and self.onboarding_session.selected_designation_category:
                self.fields['designation_category'].initial = self.onboarding_session.selected_designation_category
                self.initial['designation_category'] = self.onboarding_session.selected_designation_category.pk
                
            if 'designation_subcategory' in self.fields and self.onboarding_session.selected_designation_subcategory:
                self.fields['designation_subcategory'].initial = self.onboarding_session.selected_designation_subcategory
                self.initial['designation_subcategory'] = self.onboarding_session.selected_designation_subcategory.pk
        
        # Add designated-specific help text
        self.fields['high_school_name'].help_text = 'Name of high school attended (if applicable)'
        self.fields['supervisor_name'].help_text = 'Full name and title of your professional supervisor'
        self.fields['supervision_hours_received'].help_text = 'Total number of formal supervision hours received'
        self.fields['professional_development_plans'].help_text = 'Describe your plans for continuing professional development'
        
        # Set some fields as optional
        self.fields['high_school_name'].required = False
        self.fields['high_school_year_completed'].required = False
        self.fields['supervision_period_end'].required = False
        self.fields['other_professional_memberships'].required = False
        
        # CRITICAL: Make designation fields optional since they're set from onboarding session
        if 'designation_category' in self.fields:
            self.fields['designation_category'].required = False
            self.fields['designation_category'].help_text = 'Set during onboarding process'
            
        if 'designation_subcategory' in self.fields:
            self.fields['designation_subcategory'].required = False
            self.fields['designation_subcategory'].help_text = 'Set during onboarding process'
    
    def clean(self):
        """Designated application specific validation"""
        cleaned_data = super().clean()
        
        # CRITICAL: Force designation fields from onboarding session
        if self.onboarding_session:
            if self.onboarding_session.selected_designation_category:
                cleaned_data['designation_category'] = self.onboarding_session.selected_designation_category
            if self.onboarding_session.selected_designation_subcategory:
                cleaned_data['designation_subcategory'] = self.onboarding_session.selected_designation_subcategory
        
        # Validate supervision period
        start_date = cleaned_data.get('supervision_period_start')
        end_date = cleaned_data.get('supervision_period_end')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({
                'supervision_period_end': 'End date must be after start date.'
            })
        
        # Validate high school year
        high_school_year = cleaned_data.get('high_school_year_completed')
        if high_school_year:
            current_year = timezone.now().year
            if high_school_year > current_year:
                raise ValidationError({
                    'high_school_year_completed': 'Year cannot be in the future.'
                })
            elif high_school_year < 1950:
                raise ValidationError({
                    'high_school_year_completed': 'Please verify the year.'
                })
        
        return cleaned_data
    
    class Meta(BaseApplicationForm.Meta):
        model = DesignatedApplication
        fields = BaseApplicationForm.Meta.fields + [
            'designation_category', 'designation_subcategory',
            'high_school_name', 'high_school_year_completed',
            'supervisor_name', 'supervisor_qualification', 'supervisor_email', 
            'supervisor_phone', 'supervisor_address',
            'supervision_hours_received', 'supervision_period_start', 'supervision_period_end',
            'professional_development_plans', 'other_professional_memberships'
        ]
        widgets = {
            **BaseApplicationForm.Meta.widgets,
            'designation_category': SELECT_WIDGET,
            'designation_subcategory': SELECT_WIDGET,
            'high_school_name': TEXT_INPUT_WIDGET,
            'high_school_year_completed': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "1950", "max": str(timezone.now().year)
            }),
            'supervisor_name': TEXT_INPUT_WIDGET,
            'supervisor_qualification': TEXT_INPUT_WIDGET,
            'supervisor_email': EMAIL_WIDGET,
            'supervisor_phone': TEXT_INPUT_WIDGET,
            'supervisor_address': TEXTAREA_WIDGET,
            'supervision_hours_received': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "0"
            }),
            'supervision_period_start': DATE_WIDGET,
            'supervision_period_end': DATE_WIDGET,
            'professional_development_plans': TEXTAREA_WIDGET,
            'other_professional_memberships': TEXTAREA_WIDGET,
        }


        
# ============================================================================
# RELATED MODEL FORMS
# ============================================================================

class AcademicQualificationForm(forms.ModelForm):
    """Form for adding academic qualifications to designated applications"""
    
    class Meta:
        model = AcademicQualification
        fields = [
            'qualification_type', 'qualification_name', 'institution_name',
            'institution_address', 'date_awarded', 'grade_or_class'
        ]
        widgets = {
            'qualification_type': SELECT_WIDGET,
            'qualification_name': TEXT_INPUT_WIDGET,
            'institution_name': TEXT_INPUT_WIDGET,
            'institution_address': TEXTAREA_WIDGET,
            'date_awarded': DATE_WIDGET,
            'grade_or_class': TEXT_INPUT_WIDGET,
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['qualification_name'].help_text = 'e.g., BSc Theology, Diploma in Pastoral Care'
        self.fields['institution_address'].help_text = 'Full address of the institution'
        self.fields['grade_or_class'].help_text = 'Grade achieved or class of degree (optional)'
        
        # Mark required fields
        for field_name in ['qualification_type', 'qualification_name', 'institution_name', 'date_awarded']:
            self.fields[field_name].required = True
            if self.fields[field_name].label:
                self.fields[field_name].label = f"{self.fields[field_name].label} *"
    
    def clean_date_awarded(self):
        """Validate qualification date"""
        date_awarded = self.cleaned_data.get('date_awarded')
        if date_awarded:
            if date_awarded > timezone.now().date():
                raise ValidationError("Qualification date cannot be in the future.")
        return date_awarded


class ReferenceForm(forms.ModelForm):
    """Form for adding references to applications"""
    
    class Meta:
        model = Reference
        fields = [
            'reference_title', 'reference_surname', 'reference_names',
            'reference_email', 'reference_phone',
            'nature_of_relationship', 'letter_required'
        ]
        widgets = {
            'reference_title': SELECT_WIDGET,
            'reference_surname': TEXT_INPUT_WIDGET,
            'reference_names': TEXT_INPUT_WIDGET,
            'reference_email': EMAIL_WIDGET,
            'reference_phone': TEXT_INPUT_WIDGET,
            'nature_of_relationship': TEXT_INPUT_WIDGET,
            'letter_required': CHECKBOX_WIDGET,
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['reference_names'].help_text = 'Full first names and middle names'
        self.fields['nature_of_relationship'].help_text = 'How you know this person (e.g., supervisor, colleague, pastor)'
        self.fields['letter_required'].help_text = 'Check if a formal reference letter is required'
        
        # Mark required fields
        required_fields = [
            'reference_title', 'reference_surname', 'reference_names',
            'reference_email', 'reference_phone',
            'nature_of_relationship'
        ]
        for field_name in required_fields:
            self.fields[field_name].required = True
            if self.fields[field_name].label:
                self.fields[field_name].label = f"{self.fields[field_name].label} *"
    
    def clean_reference_email(self):
        """Validate and normalize reference email"""
        email = self.cleaned_data.get('reference_email')
        if email:
            return email.lower().strip()
        return email


class PracticalExperienceForm(forms.ModelForm):
    """Form for adding practical experience to designated applications"""
    
    class Meta:
        model = PracticalExperience
        fields = [
            'institution_name', 'contact_person_name', 'contact_person_email',
            'contact_person_phone', 'basic_nature_of_work', 'start_date',
            'end_date', 'hours_per_week'
        ]
        widgets = {
            'institution_name': TEXT_INPUT_WIDGET,
            'contact_person_name': TEXT_INPUT_WIDGET,
            'contact_person_email': EMAIL_WIDGET,
            'contact_person_phone': TEXT_INPUT_WIDGET,
            'basic_nature_of_work': TEXTAREA_WIDGET,
            'start_date': DATE_WIDGET,
            'end_date': DATE_WIDGET,
            'hours_per_week': forms.NumberInput(attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "min": "1", "max": "168"
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['basic_nature_of_work'].help_text = 'Describe the type of ministry or counselling work performed'
        self.fields['end_date'].help_text = 'Leave blank if currently ongoing'
        self.fields['hours_per_week'].help_text = 'Average hours per week (optional)'
        
        # Mark required fields
        required_fields = [
            'institution_name', 'contact_person_name', 'contact_person_email',
            'contact_person_phone', 'basic_nature_of_work', 'start_date'
        ]
        for field_name in required_fields:
            self.fields[field_name].required = True
            if self.fields[field_name].label:
                self.fields[field_name].label = f"{self.fields[field_name].label} *"
        
        # Optional fields
        self.fields['end_date'].required = False
        self.fields['hours_per_week'].required = False
    
    def clean(self):
        """Validate date ranges"""
        cleaned_data = super().clean()
        
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        return cleaned_data


# ============================================================================
# DOCUMENT MANAGEMENT FORMS
# ============================================================================

class DocumentForm(forms.ModelForm):
    """Enhanced document upload form with better categorization"""
    
    class Meta:
        model = Document
        fields = ['category', 'title', 'description', 'file', 'is_required']
        widgets = {
            'category': SELECT_WIDGET,
            'title': TEXT_INPUT_WIDGET,
            'description': TEXTAREA_WIDGET,
            'file': forms.FileInput(attrs={
                'class': 'form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors',
                'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png,.gif'
            }),
            'is_required': CHECKBOX_WIDGET,
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text
        self.fields['title'].help_text = 'Descriptive name for this document'
        self.fields['description'].help_text = 'Optional: Brief description of document contents'
        self.fields['file'].help_text = 'Supported formats: PDF, DOC, DOCX, JPG, JPEG, PNG, GIF. Max size: 10MB'
        self.fields['is_required'].help_text = 'Mark as required document for this application'
        
        # Required fields
        self.fields['category'].required = True
        self.fields['title'].required = True
        self.fields['file'].required = True
    
    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (10MB limit)
            if file.size > 10 * 1024 * 1024:
                raise ValidationError("File size cannot exceed 10MB.")
            
            # Check file extension
            allowed_extensions = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'gif']
            file_extension = os.path.splitext(file.name)[1].lower().lstrip('.')
            
            if file_extension not in allowed_extensions:
                raise ValidationError(f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}")
        
        return file


class BulkDocumentUploadForm(forms.Form):
    """Form for uploading multiple documents at once"""
    
    documents = MultipleFileField(
        required=True,
        help_text="Upload multiple documents. Hold Ctrl to select multiple files. Max 10 files, 10MB each."
    )
    default_category = forms.ChoiceField(
        choices=Document.DOCUMENT_CATEGORIES,
        widget=SELECT_WIDGET,
        required=True,
        help_text="Default category for all uploaded documents (can be changed individually later)"
    )
    
    def clean_documents(self):
        """Validate multiple document uploads"""
        files = self.cleaned_data.get('documents', [])
        
        if not files:
            raise ValidationError("No files were uploaded.")
        
        if len(files) > 10:
            raise ValidationError("You can upload a maximum of 10 files at once.")
        
        # Validate each file
        for file in files:
            if file:
                # Check file size
                if file.size > 10 * 1024 * 1024:
                    raise ValidationError(f"File {file.name} exceeds the maximum size of 10MB.")
                
                # Check file extension
                allowed_extensions = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'gif']
                file_extension = os.path.splitext(file.name)[1].lower().lstrip('.')
                
                if file_extension not in allowed_extensions:
                    raise ValidationError(f"File {file.name} has an invalid file type.")
        
        return files


# ============================================================================
# FORMSETS FOR RELATED MODELS
# ============================================================================

# Academic Qualifications Formset (for designated applications)
AcademicQualificationFormSet = inlineformset_factory(
    DesignatedApplication,
    AcademicQualification,
    form=AcademicQualificationForm,
    fields=['qualification_type', 'qualification_name', 'institution_name', 'institution_address', 'date_awarded', 'grade_or_class'],
    extra=2,
    can_delete=True,
    max_num=10,
    validate_max=True,
)

# References Formset (polymorphic - works with any application type)
ReferenceFormSet = generic_inlineformset_factory(
    Reference,
    form=ReferenceForm,
    ct_field='content_type',
    fk_field='object_id',
    fields=['reference_title', 'reference_surname', 'reference_names', 'reference_email', 'reference_phone', 'nature_of_relationship', 'letter_required'],
    extra=2,
    can_delete=True,
    max_num=5,
    validate_max=True,
)

# Practical Experience Formset (for designated applications)
PracticalExperienceFormSet = inlineformset_factory(
    DesignatedApplication,
    PracticalExperience,
    form=PracticalExperienceForm,
    fields=['institution_name', 'contact_person_name', 'contact_person_email', 'contact_person_phone', 'basic_nature_of_work', 'start_date', 'end_date', 'hours_per_week'],
    extra=1,
    can_delete=True,
    max_num=10,
    validate_max=True,
)

# Documents Formset (polymorphic - works with any application type)
DocumentFormSet = generic_inlineformset_factory(
    Document,
    form=DocumentForm,
    ct_field='content_type',
    fk_field='object_id',
    fields=['category', 'title', 'description', 'file', 'is_required'],
    extra=3,
    can_delete=True,
    max_num=20,
    validate_max=True,
)


# ============================================================================
# UTILITY FORMS
# ============================================================================

class ApplicationSearchForm(forms.Form):
    """Form for searching and filtering applications"""
    
    search_query = forms.CharField(
        max_length=200,
        required=False,
        widget=TEXT_INPUT_WIDGET,
        help_text="Search by name, email, or application number"
    )
    
    council = forms.ModelChoiceField(
        queryset=Council.objects.filter(is_active=True),
        required=False,
        empty_label="All Councils",
        widget=SELECT_WIDGET
    )
    
    affiliation_type = forms.ModelChoiceField(
        queryset=AffiliationType.objects.filter(is_active=True),
        required=False,
        empty_label="All Affiliation Types",
        widget=SELECT_WIDGET
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + BaseApplication.STATUS_CHOICES,
        required=False,
        widget=SELECT_WIDGET
    )
    
    date_from = forms.DateField(
        required=False,
        widget=DATE_WIDGET,
        help_text="Applications submitted from this date"
    )
    
    date_to = forms.DateField(
        required=False,
        widget=DATE_WIDGET,
        help_text="Applications submitted to this date"
    )

class ApplicationReviewForm(forms.Form):
    """Form for reviewing and updating application status with digital card assignment"""
    
    status = forms.ChoiceField(
        choices=[
            ('under_review', 'Under Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('requires_clarification', 'Requires Clarification'),
        ],
        widget=SELECT_WIDGET,
        required=True
    )
    
    reviewer_notes = forms.CharField(
        widget=TEXTAREA_WIDGET,
        required=False,
        help_text="Internal notes for review team"
    )
    
    rejection_reason = forms.CharField(
        widget=TEXTAREA_WIDGET,
        required=False,
        help_text="Reason for rejection (visible to applicant)"
    )
    
    assign_digital_card = forms.BooleanField(
        initial=False,
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        help_text="Check to automatically create and send a digital affiliation card"
    )

    def __init__(self, *args, **kwargs):
        self.application = kwargs.pop('application', None)
        super().__init__(*args, **kwargs)
        
        # Check for existing card and modify form accordingly
        if self.application:
            existing_card = self.check_existing_card()
            if existing_card:
                # Card already exists - hide the checkbox and show info
                self.fields['assign_digital_card'].widget = forms.HiddenInput()
                self.fields['assign_digital_card'].initial = True
                self.fields['assign_digital_card'].help_text = f"Card already assigned: {existing_card.card_number}"
                # Add a flag to indicate card exists
                self.existing_card = existing_card
            else:
                self.existing_card = None
    
    def check_existing_card(self):
        """Check if application already has an assigned card"""
        if not self.application:
            return None
            
        try:
            from django.contrib.contenttypes.models import ContentType
            from affiliationcard.models import AffiliationCard
            
            content_type = ContentType.objects.get_for_model(self.application)
            return AffiliationCard.objects.filter(
                content_type=content_type,
                object_id=self.application.pk,
                status__in=['assigned', 'active']
            ).first()
        except ImportError:
            # affiliationcard app not available
            return None
    
    def clean(self):
        """Validate review form"""
        cleaned_data = super().clean()
        
        status = cleaned_data.get('status')
        rejection_reason = cleaned_data.get('rejection_reason')
        assign_card = cleaned_data.get('assign_digital_card', False)
        
        # Validate rejection reason
        if status == 'rejected' and not rejection_reason:
            raise ValidationError({
                'rejection_reason': 'Rejection reason is required when rejecting an application.'
            })
        
        # Validate card assignment - only allow if approving
        if assign_card and status != 'approved':
            raise ValidationError({
                'assign_digital_card': 'Digital cards can only be assigned when approving applications.'
            })
        
        return cleaned_data