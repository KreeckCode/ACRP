from django import forms
from .models import (
    Provider, ProviderAccreditation,
    Qualification, QualificationModule,
    ProviderUserProfile, AssessorProfile,
    ProviderDocument
)
from .models import ApplicationLink

class ApplicationLinkForm(forms.ModelForm):
    class Meta:
        model = ApplicationLink
        exclude = ('token', 'uses', 'created_at', 'created_by')
        widgets = {
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

class ProviderForm(forms.ModelForm):
    class Meta:
        model   = Provider
        exclude = ('created_at','updated_at','created_by','updated_by')

class AccreditationForm(forms.ModelForm):
    class Meta:
        model   = ProviderAccreditation
        fields  = '__all__'

class QualificationForm(forms.ModelForm):
    class Meta:
        model   = Qualification
        exclude = ('created_at','updated_at',)

class ModuleForm(forms.ModelForm):
    class Meta:
        model  = QualificationModule
        fields = '__all__'

class ProviderUserForm(forms.ModelForm):
    class Meta:
        model  = ProviderUserProfile
        fields = '__all__'

class AssessorForm(forms.ModelForm):
    class Meta:
        model   = AssessorProfile
        exclude = ('user',)

class ProviderDocumentForm(forms.ModelForm):
    class Meta:
        model   = ProviderDocument
        fields  = ['name','file']
