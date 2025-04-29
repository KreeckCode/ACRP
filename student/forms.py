from django import forms
from accounts.models import User
from providers.models import Qualification
from .models import (
    LearnerProfile, AcademicHistory,
    LearnerQualificationEnrollment,
    CPDEvent, CPDHistory,
    LearnerAffiliation, DocumentType,
    LearnerDocument
)
from django.core.exceptions import ValidationError
from providers.models import ApplicationLink

class LearnerRegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, label="First name")
    last_name  = forms.CharField(max_length=150, label="Last name")
    email      = forms.EmailField(label="Email address")

    # POPI Act consent (step 2)
    popi_consent = forms.BooleanField(
        label=(
            "I consent to the processing and storage of my personal "
            "information in accordance with the Protection of Personal "
            "Information Act (POPI)."
        ),
        required=True
    )

    # hidden but validated
    token      = forms.UUIDField(widget=forms.HiddenInput)
    provider   = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model  = LearnerProfile
        fields = [
            'provider',
            'id_number',
            'date_of_birth',
            'gender',
            'phone',
            'address',
            'nationality',
            'primary_language',
            'emergency_name',
            'emergency_relation',
            'emergency_phone',
            'token',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type':'date'}),
        }

    def clean_token(self):
        t = self.cleaned_data.get('token')
        try:
            link = ApplicationLink.objects.get(token=t)
        except ApplicationLink.DoesNotExist:
            raise ValidationError("Invalid registration link.")
        if not link.can_use():
            raise ValidationError("This link has expired or is inactive.")
        self.link = link
        return t

    def clean_provider(self):
        prov_id = self.cleaned_data.get('provider')
        # ensure provider matches link
        if hasattr(self, 'link') and self.link.provider_id != prov_id:
            raise ValidationError("Mismatched provider.")
        return prov_id

    def save(self, commit=True):
        # 1) create the User
        first_name = self.cleaned_data['first_name']
        last_name  = self.cleaned_data['last_name']
        email      = self.cleaned_data['email']
        id_number  = self.cleaned_data['id_number']

        # username = email, password = id_number
        raw_password = id_number

        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=raw_password,
        )
        # ensure learner only gets activated once you verify them
        user.is_active = False
        user.save()

        # 2) create the LearnerProfile
        profile = super().save(commit=False)
        profile.user = user
        profile.verification_status = LearnerProfile.verification_status.field.default
        profile.status = LearnerProfile.status.field.default
        if commit:
            profile.save()
            # consume the link
            self.link.use()

        return profile
class LearnerProfileForm(forms.ModelForm):
    class Meta:
        model  = LearnerProfile
        exclude=()

class AcademicHistoryForm(forms.ModelForm):
    class Meta:
        model  = AcademicHistory
        exclude=()

class EnrollmentForm(forms.ModelForm):
    # manually declare the qualification field
    qualification = forms.ModelChoiceField(
        queryset=Qualification.objects.all(),
        label="Qualification"
    )

    class Meta:
        model   = LearnerQualificationEnrollment
        exclude = ('learner',) 

class CPDEventForm(forms.ModelForm):
    class Meta:
        model  = CPDEvent
        exclude=()

class CPDHistoryForm(forms.ModelForm):
    class Meta:
        model  = CPDHistory
        exclude=()

class AffiliationForm(forms.ModelForm):
    class Meta:
        model  = LearnerAffiliation
        exclude=()

class DocumentTypeForm(forms.ModelForm):
    class Meta:
        model  = DocumentType
        exclude=()

class LearnerDocumentForm(forms.ModelForm):
    class Meta:
        model  = LearnerDocument
        exclude=()
