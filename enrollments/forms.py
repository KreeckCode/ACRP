# enrollments/forms.py - Updated with enhanced functionality
import os
from django import forms
from django.contrib.contenttypes.forms import generic_inlineformset_factory
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from .models import (
    CGMPAffiliation,
    CPSCAffiliation,
    CMTPAffiliation,
    Document,
    RegistrationSession,
)
from django.utils.translation import gettext_lazy as _

# Enhanced HTML5 widgets
DATE_WIDGET = forms.DateInput(attrs={
    "type": "date", 
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
    "placeholder": "Select date"
})

TEXTAREA_WIDGET = forms.Textarea(attrs={
    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
    "rows": 4, 
    "placeholder": "Enter details..."
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

# Multiple file upload widgets
class MultipleFileInput(forms.ClearableFileInput):
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
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)
    
    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


# Base Form Class for common functionality
class BaseAffiliationForm(forms.ModelForm):
    """
    Base form class containing common fields and validation logic.
    Implements DRY principles and ensures consistency across council forms.
    """

    def __init__(self, *args, request=None, **kwargs):
        # capture request if passed, then remove it
        self.request = request
        super().__init__(*args, **kwargs)

        # Apply modern styling to all fields
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                    "rows": 4
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })
            elif isinstance(field.widget, forms.EmailInput):
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    "class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                })
            elif isinstance(field.widget, forms.DateInput):
                field.widget.attrs.update({
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                })

        # Set required fields styling
        for field_name, field in self.fields.items():
            if field.required:
                field.widget.attrs.update({"required": True})
                # Add asterisk to label for required fields
                if field.label:
                    field.label = f"{field.label} *"

    def clean_email(self):
        """Validate email format and uniqueness"""
        email = self.cleaned_data.get("email")
        if email:
            # Normalize email to lowercase for comparison
            email = email.lower().strip()
            # Check if email already exists (excluding current instance if editing)
            existing_query = self._meta.model.objects.filter(email__iexact=email)
            if self.instance and self.instance.pk:
                existing_query = existing_query.exclude(pk=self.instance.pk)

            if existing_query.exists():
                raise ValidationError("This email address is already registered.")
        return email

    def clean_id_number(self):
        """Validate ID number format and uniqueness"""
        id_number = self.cleaned_data.get("id_number")
        if id_number:
            # Sanitize ID number by removing spaces and dashes
            id_number = id_number.replace(" ", "").replace("-", "")

            # Basic South African ID validation (13 digits)
            if not id_number.isdigit() or len(id_number) != 13:
                raise ValidationError(
                    "Please enter a valid 13-digit South African ID number."
                )

            # Check uniqueness
            existing_query = self._meta.model.objects.filter(id_number=id_number)
            if self.instance and self.instance.pk:
                existing_query = existing_query.exclude(pk=self.instance.pk)

            if existing_query.exists():
                raise ValidationError("This ID number is already registered.")
        return id_number

    def clean_date_of_birth(self):
        """Validate date of birth"""
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = timezone.now().date()
            age = (
                today.year
                - dob.year
                - ((today.month, today.day) < (dob.month, dob.day))
            )

            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
            if age < 16:
                raise ValidationError("Applicant must be at least 16 years old.")
            if age > 100:
                raise ValidationError("Please verify the date of birth.")
        return dob

    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()

        # Validate disciplinary action
        disciplinary_action = cleaned_data.get("disciplinary_action")
        disciplinary_description = cleaned_data.get("disciplinary_description")

        if disciplinary_action and not disciplinary_description:
            raise ValidationError(
                {
                    "disciplinary_description": "Please provide details about the disciplinary action."
                }
            )

        # Validate felony conviction
        felony_conviction = cleaned_data.get("felony_conviction")
        felony_description = cleaned_data.get("felony_description")

        if felony_conviction and not felony_description:
            raise ValidationError(
                {
                    "felony_description": "Please provide details about the felony conviction."
                }
            )

        # Validate legal agreements
        if not cleaned_data.get('popi_act_accepted'):
            raise ValidationError(
                {"popi_act_accepted": "You must agree to the POPIA Act to continue."}
            )
            
        if not cleaned_data.get('terms_accepted'):
            raise ValidationError(
                {"terms_accepted": "You must agree to the Terms and Conditions."}
            )
            
        if not cleaned_data.get('information_accurate'):
            raise ValidationError(
                {"information_accurate": "You must certify that all information is accurate."}
            )

        return cleaned_data

    class Meta:
        abstract = True
        widgets = {
            "date_of_birth": DATE_WIDGET,
            "qualification_date": DATE_WIDGET,
            "disciplinary_description": TEXTAREA_WIDGET,
            "felony_description": TEXTAREA_WIDGET,
            "work_description": TEXTAREA_WIDGET,
            "postal_address": TEXTAREA_WIDGET,
            "street_address": TEXTAREA_WIDGET,
            "email": EMAIL_WIDGET,
            "title": SELECT_WIDGET,
            "gender": SELECT_WIDGET,
            "initials": TEXT_INPUT_WIDGET,
            "first_name": TEXT_INPUT_WIDGET,
            "last_name": TEXT_INPUT_WIDGET,
            "preferred_name": TEXT_INPUT_WIDGET,
            "id_number": TEXT_INPUT_WIDGET,
            "passport_number": TEXT_INPUT_WIDGET,
            "race": TEXT_INPUT_WIDGET,
            "disability": TEXT_INPUT_WIDGET,
            "cell": TEXT_INPUT_WIDGET,
            "tel_work": TEXT_INPUT_WIDGET,
            "tel_home": TEXT_INPUT_WIDGET,
            "fax": TEXT_INPUT_WIDGET,
            "website": TEXT_INPUT_WIDGET,
            "postal_code": TEXT_INPUT_WIDGET,
            "province": TEXT_INPUT_WIDGET,
            "country": TEXT_INPUT_WIDGET,
            "religious_affiliation": TEXT_INPUT_WIDGET,
            "home_language": TEXT_INPUT_WIDGET,
            "other_languages": TEXT_INPUT_WIDGET,
            "highest_qualification": TEXT_INPUT_WIDGET,
            "qualification_institution": TEXT_INPUT_WIDGET,
            "occupation": TEXT_INPUT_WIDGET,
            "popi_act_accepted": CHECKBOX_WIDGET,
            "terms_accepted": CHECKBOX_WIDGET,
            "information_accurate": CHECKBOX_WIDGET,
            "disciplinary_action": CHECKBOX_WIDGET,
            "felony_conviction": CHECKBOX_WIDGET,
        }


# CGMP Form - ENHANCED WITH FILE UPLOAD
class CGMPForm(BaseAffiliationForm):
    """Form for Council for General Ministry Professionals with integrated file upload."""

    # INTEGRATED FILE UPLOAD FIELD
    documents = MultipleFileField(
        required=False,
        help_text=_("Upload required documents (ID, qualifications, certificates, references). Max 10 files, 10MB each."),
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'gif']
            )
        ]
    )

    class Meta:
        model = CGMPAffiliation
        # UPDATED FIELD LIST - Fixed field names to match model
        fields = [
            # --- Personal Information ---
            'title', 'gender', 'initials', 'first_name', 'last_name',
            'preferred_name', 'id_number', 'passport_number', 'date_of_birth',
            'race', 'disability',
            # --- Contact Information ---
            'email', 'cell', 'tel_work', 'tel_home', 'fax', 'website',
            'postal_address', 'street_address', 'postal_code', 'province', 'country',
            # --- Background Info ---
            'religious_affiliation', 'home_language', 'other_languages',
            # --- Qualifications & Work ---
            'highest_qualification', 'qualification_date', 'qualification_institution',
            'occupation', 'work_description',
            # --- Ministry Experience ---
            'years_ministry', 'months_ministry',
            # --- Background Checks ---
            'disciplinary_action', 'disciplinary_description',
            'felony_conviction', 'felony_description',
            # --- CGMP‑Specific Ministry Fields ---
            'ordination_status', 'ordination_date', 'ordaining_body',
            'current_ministry_role', 'congregation_name', 'denomination',
            'involved_pastoral', 'pastoral_responsibilities', 'preaching_frequency',
            'registered_elsewhere', 'other_registrations', 'continuing_education',
            # --- LEGAL AGREEMENTS - FIXED FIELD NAMES ---
            'popi_act_accepted', 'terms_accepted', 'information_accurate',
        ]
        widgets = {
            **BaseAffiliationForm.Meta.widgets,
            'ordination_status': SELECT_WIDGET,
            'ordination_date': DATE_WIDGET,
            'ordaining_body': TEXT_INPUT_WIDGET,
            'current_ministry_role': TEXT_INPUT_WIDGET,
            'congregation_name': TEXT_INPUT_WIDGET,
            'denomination': TEXT_INPUT_WIDGET,
            'pastoral_responsibilities': TEXTAREA_WIDGET,
            'preaching_frequency': SELECT_WIDGET,
            'other_registrations': TEXTAREA_WIDGET,
            'involved_pastoral': CHECKBOX_WIDGET,
            'registered_elsewhere': CHECKBOX_WIDGET,
            'continuing_education': CHECKBOX_WIDGET,
        }

    def __init__(self, *args, **kwargs):
        # allow request to be passed in
        super().__init__(*args, **kwargs)

        # Make ordination_date, pastoral_responsibilities, other_registrations optional
        self.fields['ordination_date'].required = False
        self.fields['ordination_date'].help_text = _("Required for ordained/licensed status")

        self.fields['ordaining_body'].required = False
        self.fields['ordaining_body'].help_text = _("Required for ordained/licensed status")

        self.fields['pastoral_responsibilities'].required = False
        self.fields['pastoral_responsibilities'].help_text = _("Required if involved in pastoral work")

        self.fields['other_registrations'].required = False
        self.fields['other_registrations'].help_text = _("List other professional registrations")

    def clean_documents(self):
        """Validate uploaded documents"""
        files = self.cleaned_data.get('documents', [])
        
        if not files:
            return files
        
        # Ensure files is a list
        if not isinstance(files, list):
            files = [files]
        
        # Validate file count
        if len(files) > 10:
            raise ValidationError(
                _("You can upload a maximum of 10 files."),
                code='too_many_files'
            )
        
        # Validate each file
        for file in files:
            if file:
                # Check file size (10MB limit)
                if file.size > 10 * 1024 * 1024:
                    raise ValidationError(
                        _("File '%(filename)s' exceeds the maximum size of 10MB.") % {'filename': file.name},
                        code='file_too_large'
                    )
                
                # Check file extension
                allowed_extensions = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'gif']
                file_extension = os.path.splitext(file.name)[1].lower().lstrip('.')
                
                if file_extension not in allowed_extensions:
                    raise ValidationError(
                        _("File '%(filename)s' has an invalid extension. Allowed: %(extensions)s") % {
                            'filename': file.name,
                            'extensions': ', '.join(allowed_extensions)
                        },
                        code='invalid_extension'
                    )
        
        return files

    def clean(self):
        cleaned = super().clean()

        # ordination logic
        status = cleaned.get('ordination_status')
        if status in ('ordained', 'licensed'):
            if not cleaned.get('ordination_date'):
                self.add_error('ordination_date', _("Ordination date is required for this status."))
            if not cleaned.get('ordaining_body'):
                self.add_error('ordaining_body', _("Ordaining body is required for this status."))

        # pastoral involvement
        if cleaned.get('involved_pastoral') and not cleaned.get('pastoral_responsibilities'):
            self.add_error('pastoral_responsibilities', _("Please describe your pastoral responsibilities."))

        return cleaned

    def save(self, commit=True):
        """Enhanced save method with document handling"""
        instance = super().save(commit=commit)
        
        if commit:
            # Handle file uploads
            documents = self.cleaned_data.get('documents', [])
            if documents:
                self._save_documents(instance, documents)
        
        return instance
    
    def _save_documents(self, instance, documents):
        """Save uploaded documents"""
        if not isinstance(documents, list):
            documents = [documents]
        
        for file in documents:
            if file:
                # Determine document category based on filename
                category = self._determine_document_category(file.name)
                
                # Create document instance
                Document.objects.create(
                    content_object=instance,
                    category=category,
                    file=file,
                    uploaded_by=getattr(self.request, 'user', None) if self.request else None,
                    description=f"Uploaded during CGMP application"
                )
    
    def _determine_document_category(self, filename):
        """Determine document category based on filename"""
        filename_lower = filename.lower()
        
        if any(word in filename_lower for word in ['id', 'identity', 'passport']):
            return 'id_document'
        elif any(word in filename_lower for word in ['certificate', 'qualification', 'degree', 'diploma']):
            return 'qualification'
        elif any(word in filename_lower for word in ['ordination', 'ordain']):
            return 'ordination'
        elif any(word in filename_lower for word in ['reference', 'recommendation']):
            return 'reference'
        elif any(word in filename_lower for word in ['transcript']):
            return 'transcript'
        else:
            return 'supporting'


# CPSC Form - KEPT INTACT, JUST ENHANCED STYLING
class CPSCForm(BaseAffiliationForm):
    """Form for Council for Pastoral & Spiritual Care"""

    class Meta:
        model = CPSCAffiliation
        exclude = [
            "approved",
            "approved_at",
            "approved_by",
            "created_user",
            "created_at",
            "updated_at",
            "documents",
        ]
        widgets = {
            **BaseAffiliationForm.Meta.widgets,
            "certification_date": DATE_WIDGET,
            "specialization_areas": TEXTAREA_WIDGET,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add help text to specific fields
        if "certification_date" in self.fields:
            self.fields["certification_date"].help_text = (
                "Date when certification was obtained"
            )
            self.fields["certification_date"].required = False

        if "specialization_areas" in self.fields:
            self.fields["specialization_areas"].help_text = (
                "List your areas of specialization in pastoral care and counseling"
            )
            self.fields["specialization_areas"].required = False

    def clean(self):
        cleaned_data = super().clean()

        # CPSC-specific validations
        counseling_certification = cleaned_data.get("counseling_certification")
        certification_body = cleaned_data.get("certification_body")

        if counseling_certification and counseling_certification != "none":
            if not certification_body:
                raise ValidationError(
                    {"certification_body": "Please specify the certification body."}
                )

        # Validate supervision requirements
        clinical_supervision = cleaned_data.get("clinical_supervision")
        supervisor_name = cleaned_data.get("supervisor_name")

        if clinical_supervision:
            if not supervisor_name:
                raise ValidationError(
                    {
                        "supervisor_name": "Supervisor name is required when under clinical supervision."
                    }
                )

        # Validate insurance requirements
        professional_liability_insurance = cleaned_data.get(
            "professional_liability_insurance"
        )
        insurance_provider = cleaned_data.get("insurance_provider")

        if professional_liability_insurance and not insurance_provider:
            raise ValidationError(
                {"insurance_provider": "Please specify your insurance provider."}
            )

        return cleaned_data


# CMTP Form - KEPT INTACT, JUST ENHANCED STYLING
class CMTPForm(BaseAffiliationForm):
    """Form for Council for Ministry Training Providers"""

    class Meta:
        model = CMTPAffiliation
        exclude = [
            "approved",
            "approved_at",
            "approved_by",
            "created_user",
            "created_at",
            "updated_at",
            "documents",
        ]
        widgets = {
            **BaseAffiliationForm.Meta.widgets,
            "institution_address": TEXTAREA_WIDGET,
            "teaching_subjects": TEXTAREA_WIDGET,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add help text to specific fields
        if "institution_address" in self.fields:
            self.fields["institution_address"].help_text = (
                "Full address of your training institution"
            )

        if "teaching_subjects" in self.fields:
            self.fields["teaching_subjects"].help_text = (
                "List the subjects/courses you teach (one per line)"
            )

    def clean(self):
        cleaned_data = super().clean()

        # CMTP-specific validations
        institution_accredited = cleaned_data.get("institution_accredited")
        accreditation_body = cleaned_data.get("accreditation_body")

        if institution_accredited and not accreditation_body:
            raise ValidationError(
                {"accreditation_body": "Please specify the accreditation body."}
            )

        # Validate student capacity
        current_student_count = cleaned_data.get("current_student_count")
        max_student_capacity = cleaned_data.get("max_student_capacity")

        if current_student_count is not None and max_student_capacity is not None:
            if current_student_count > max_student_capacity:
                raise ValidationError(
                    {
                        "current_student_count": "Current student count cannot exceed maximum capacity."
                    }
                )

        return cleaned_data


# Enhanced Document Form
class DocumentForm(forms.ModelForm):
    """Enhanced document upload form with validation"""

    ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif"]
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    class Meta:
        model = Document
        fields = ["category", "file", "description"]
        widgets = {
            "category": SELECT_WIDGET,
            "file": forms.FileInput(
                attrs={
                    "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                    "accept": ".pdf,.doc,.docx,.jpg,.jpeg,.png,.gif",
                }
            ),
            "description": TEXTAREA_WIDGET,
        }

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if file:
            # Check file size
            if file.size > self.MAX_FILE_SIZE:
                raise ValidationError("File size cannot exceed 10MB.")

            # Check file extension
            _, file_extension = os.path.splitext(file.name.lower())
            if file_extension not in self.ALLOWED_EXTENSIONS:
                raise ValidationError(
                    f"File type not allowed. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
                )

        return file


# Registration Session Form
class RegistrationTypeForm(forms.Form):
    """Form for selecting registration type"""

    REGISTRATION_CHOICES = [
        ("cgmp", "CGMP - General Ministry Professionals"),
        ("cpsc", "CPSC - Pastoral & Spiritual Care"),
        ("cmtp", "CMTP - Ministry Training Providers"),
        ("student", "Invited Affiliate"),
        ("provider", "Training Provider"),
    ]

    registration_type = forms.ChoiceField(
        choices=REGISTRATION_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"}),
        required=True,
        error_messages={"required": "Please select a registration type to continue."},
    )


# Council Selection Form (for Associated Affiliates)
class CouncilSelectionForm(forms.Form):
    """Form for selecting council within associated affiliation"""

    COUNCIL_CHOICES = [
        ("cgmp", "CGMP - General Ministry Professionals"),
        ("cpsc", "CPSC - Pastoral & Spiritual Care"),
        ("cmtp", "CMMP - Ministry Training Providers"),
    ]

    council_type = forms.ChoiceField(
        choices=COUNCIL_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"}),
        required=True,
        error_messages={"required": "Please select a council to continue."},
    )


# Generic inline formsets for Documents
CGMPDocFormSet = generic_inlineformset_factory(
    Document,
    form=DocumentForm,
    ct_field="content_type",
    fk_field="object_id",
    extra=3,
    can_delete=True,
    max_num=10,
    validate_max=True,
    fields=["category", "file", "description"],
)

CPSCDocFormSet = generic_inlineformset_factory(
    Document,
    form=DocumentForm,
    ct_field="content_type",
    fk_field="object_id",
    extra=1,
    can_delete=True,
    max_num=10,
    validate_max=True,
    fields=["category", "file", "description"],
)

CMTPDocFormSet = generic_inlineformset_factory(
    Document,
    form=DocumentForm,
    ct_field="content_type",
    fk_field="object_id",
    extra=1,
    can_delete=True,
    max_num=10,
    validate_max=True,
    fields=["category", "file", "description"],
)


# Document Upload Session Form
class DocumentUploadSessionForm(forms.ModelForm):
    """Form for managing document upload sessions"""

    class Meta:
        model = RegistrationSession
        fields = ["status", "notes"]
        widgets = {"status": SELECT_WIDGET, "notes": TEXTAREA_WIDGET}

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        notes = cleaned_data.get("notes")

        if status == "rejected" and not notes:
            raise ValidationError({"notes": "Please provide a reason for rejection."})

        return cleaned_data


# Document Category Selection Form
class DocumentCategorySelectionForm(forms.Form):
    """Form for selecting document categories to upload"""

    def __init__(self, council_type, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if Document model has get_categories_for_council method
        if hasattr(Document, "get_categories_for_council"):
            choices = Document.get_categories_for_council(council_type)
        else:
            # Fallback to basic choices if method doesn't exist
            choices = [
                ("qualification", "Academic Qualification"),
                ("id_document", "Identity Document"),
                ("certification", "Professional Certificate"),
                ("reference", "Reference Letter"),
                ("supporting", "Other Documentation"),
            ]

        self.fields["categories"] = forms.MultipleChoiceField(
            choices=choices,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"}),
            required=True,
            error_messages={
                "required": "Please select at least one document category."
            },
        )

    def clean_categories(self):
        categories = self.cleaned_data.get("categories")
        if not categories:
            raise ValidationError("At least one category must be selected.")
        return categories


# Batch Document Upload Form
class BatchDocumentUploadForm(forms.Form):
    """Form for uploading multiple documents at once"""

    files = MultipleFileField(
        widget=MultipleFileInput(
            attrs={
                "class": "form-input w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors",
                "accept": ".pdf,.doc,.docx,.jpg,.jpeg,.png,.gif",
            }
        ),
        help_text="Hold Ctrl to select multiple files. Maximum 10 files, 10MB each.",
        required=True,
    )

    def clean_files(self):
        files = self.cleaned_data.get('files', [])
        
        if not files:
            raise forms.ValidationError("No files were uploaded.")

        if len(files) > 10:
            raise forms.ValidationError("You can upload a maximum of 10 files at once.")

        for file in files:
            if file and file.size > 10 * 1024 * 1024:  # 10MB
                raise forms.ValidationError(
                    f"File {file.name} exceeds the maximum size of 10MB."
                )

            # Get file extension safely
            if file:
                file_parts = file.name.lower().split(".")
                if len(file_parts) < 2:
                    raise forms.ValidationError(f"File {file.name} has no extension.")

                ext = file_parts[-1]
                if ext not in ["pdf", "doc", "docx", "jpg", "jpeg", "png", "gif"]:
                    raise forms.ValidationError(f"File {file.name} has an invalid extension.")

        return files