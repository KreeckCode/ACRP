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
        exclude = ('learner',)  # we set learner in the view, so exclude it here

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
