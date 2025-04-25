from django import forms
from django.contrib.contenttypes.forms import generic_inlineformset_factory  # for GenericFK formsets :contentReference[oaicite:5]{index=5}
from .models import (
    AssociatedAffiliation, DesignatedAffiliation,
    StudentAffiliation, Document
)

# HTML5 date widget for all date fields :contentReference[oaicite:6]{index=6}
DATE_WIDGET = forms.DateInput(attrs={'type': 'date'})

# — ASSOCIATED AFFILIATION FORM —
class AssociatedForm(forms.ModelForm):
    # ChoiceField for gender :contentReference[oaicite:7]{index=7}
    gender = forms.ChoiceField(
        choices=AssociatedAffiliation.GENDER_CHOICES,
        widget=forms.Select(),
        required=True
    )
    # Optional fields (blank=True) must be required=False :contentReference[oaicite:8]{index=8}
    disability             = forms.CharField(required=False)
    passport_number        = forms.CharField(required=False)
    tel_work               = forms.CharField(required=False)
    tel_home               = forms.CharField(required=False)
    fax                    = forms.CharField(required=False)
    religious_affiliation  = forms.CharField(required=False)
    website                = forms.URLField(required=False)
    other_languages        = forms.CharField(required=False)
    # BooleanFields as optional checkboxes :contentReference[oaicite:9]{index=9}
    disciplinary_action    = forms.BooleanField(required=False)
    disciplinary_description = forms.CharField(widget=forms.Textarea, required=False)
    felony_conviction      = forms.BooleanField(required=False)
    felony_description     = forms.CharField(widget=forms.Textarea, required=False)
    involved_pastoral      = forms.BooleanField(required=False)
    registered_elsewhere   = forms.BooleanField(required=False)
    suitably_trained       = forms.BooleanField(required=False)

    class Meta:
        model = AssociatedAffiliation
        # exclude approval & relation fields :contentReference[oaicite:10]{index=10}
        exclude = [
            'approved', 'approved_at', 'approved_by',
            'created_user', 'documents'
        ]
        widgets = {
            'date_of_birth': DATE_WIDGET,
            'qualification_date': DATE_WIDGET,
        }

# — DESIGNATED AFFILIATION FORM —
class DesignatedForm(forms.ModelForm):
    gender = forms.ChoiceField(
        choices=AssociatedForm.Meta.model.GENDER_CHOICES,
        widget=forms.Select(),
        required=True
    )
    disability = forms.CharField(required=False)
    passport_number = forms.CharField(required=False)
    tel_work = forms.CharField(required=False)
    tel_home = forms.CharField(required=False)
    fax = forms.CharField(required=False)
    religious_affiliation = forms.CharField(required=False)
    website = forms.URLField(required=False)
    other_languages = forms.CharField(required=False)
    disciplinary_action = forms.BooleanField(required=False)
    disciplinary_description = forms.CharField(widget=forms.Textarea, required=False)
    felony_conviction = forms.BooleanField(required=False)
    felony_description = forms.CharField(widget=forms.Textarea, required=False)
    involved_pastoral = forms.BooleanField(required=False)
    suitably_trained = forms.BooleanField(required=False)
    

    class Meta:
        model = DesignatedAffiliation
        exclude = [
            'approved', 'approved_at', 'approved_by',
            'created_user', 'documents'
        ]
        widgets = {
            'date_of_birth': DATE_WIDGET,
            'qualification_date': DATE_WIDGET,
            'date_commenced': DATE_WIDGET,
        }

# — STUDENT AFFILIATION FORM —
class StudentForm(forms.ModelForm):
    gender = forms.ChoiceField(
        choices=AssociatedForm.Meta.model.GENDER_CHOICES,
        widget=forms.Select(),
        required=True
    )
    disability = forms.CharField(required=False)
    passport_number = forms.CharField(required=False)
    tel_work = forms.CharField(required=False)
    tel_home = forms.CharField(required=False)
    fax = forms.CharField(required=False)
    religious_affiliation = forms.CharField(required=False)
    website = forms.URLField(required=False)
    other_languages = forms.CharField(required=False)
    disciplinary_action = forms.BooleanField(required=False)
    disciplinary_description = forms.CharField(widget=forms.Textarea, required=False)
    felony_conviction = forms.BooleanField(required=False)
    felony_description = forms.CharField(widget=forms.Textarea, required=False)
    involved_pastoral = forms.BooleanField(required=False)
    suitably_trained = forms.BooleanField(required=False)

    class Meta:
        model = StudentAffiliation
        exclude = [
            'approved', 'approved_at', 'approved_by',
            'created_user', 'documents'
        ]
        widgets = {
            'date_of_birth': DATE_WIDGET,
            'qualification_date': DATE_WIDGET,
        }

# — DOCUMENT FORM & INLINE‐FORMSETS —
class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['category', 'file']  # only these two :contentReference[oaicite:11]{index=11}

# Generic inline‐formsets for Documents (GenericFK) :contentReference[oaicite:12]{index=12}
AssocDocFormSet = generic_inlineformset_factory(
    Document, form=DocumentForm,
    ct_field="content_type", fk_field="object_id",
    extra=1, can_delete=True
)
DesigDocFormSet = generic_inlineformset_factory(
    Document, form=DocumentForm,
    ct_field="content_type", fk_field="object_id",
    extra=1, can_delete=True
)
StudentDocFormSet = generic_inlineformset_factory(
    Document, form=DocumentForm,
    ct_field="content_type", fk_field="object_id",
    extra=1, can_delete=True
)
