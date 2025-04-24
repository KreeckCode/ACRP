from django import forms
from .models import SignatureRequest, Signer

class SignatureRequestForm(forms.ModelForm):
    # Allow multiple file attachments; handled in the view.
    documents = forms.FileField(widget=forms.ClearableFileInput(), required=False)

    class Meta:
        model = SignatureRequest
        # Remove 'status' so the user cannot set it manually.
        fields = ['title', 'description', 'expiration']

class SignerForm(forms.ModelForm):
    # The signature field will store a Base64 string from the signature pad.
    signature = forms.CharField(widget=forms.HiddenInput(), required=True)

    class Meta:
        model = Signer
        fields = ['signature']
