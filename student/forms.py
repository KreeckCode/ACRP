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
from providers.models import ApplicationLink

class LearnerRegistrationForm(forms.ModelForm):
    token = forms.UUIDField(widget=forms.HiddenInput)

    class Meta:
        model  = LearnerProfile
        fields = [
            'provider','id_number','date_of_birth','gender','phone','email',
            'address','nationality','primary_language',
            'emergency_name','emergency_relation','emergency_phone','token'
        ]
        widgets = {'provider': forms.HiddenInput()}

    def clean_token(self):
        token = self.cleaned_data['token']
        try:
            link = ApplicationLink.objects.get(token=token)
        except ApplicationLink.DoesNotExist:
            raise forms.ValidationError("Invalid registration link.")
        if not link.can_use():
            raise forms.ValidationError("This link has expired or is inactive.")
        self.link = link
        return token

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.verification_status = 'PENDING'
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
