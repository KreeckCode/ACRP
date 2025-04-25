from django import forms
from .models import Provider, ProviderAccreditation, ProviderUserProfile

class ProviderForm(forms.ModelForm):
    """Form for creating/updating a Provider."""
    class Meta:
        model = Provider
        fields = [
            'code','trade_name','legal_name','registration_number',
            'vat_number','qcto_provider_code','address_line1','address_line2',
            'city','province','postal_code','country','phone','email','website','status'
        ]

class ProviderAccreditationForm(forms.ModelForm):
    """Form for adding/editing a Provider's accreditation."""
    class Meta:
        model = ProviderAccreditation
        fields = ['provider','code','name','description','accreditation_number',
                  'accrediting_body','association','start_date','expiry_date','status','document']

class ProviderUserProfileForm(forms.ModelForm):
    """Form to assign a User to a Provider with a provider-specific role."""
    class Meta:
        model = ProviderUserProfile
        fields = ['user','provider','role']