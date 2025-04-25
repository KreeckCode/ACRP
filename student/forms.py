from django import forms
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
    class Meta:
        model  = LearnerQualificationEnrollment
        exclude=()

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
