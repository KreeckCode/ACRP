from django import forms
from .models import Database, Entry


class DatabaseForm(forms.ModelForm):
    class Meta:
        model = Database
        fields = ['name', 'description', 'is_public', 'is_protected', 'password']
        widgets = {
            'password': forms.PasswordInput(render_value=True),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_protected = cleaned_data.get("is_protected")
        password = cleaned_data.get("password")

        if is_protected and not password:
            self.add_error("password", "Password is required for protected databases.")
        return cleaned_data


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ['database', 'database_type', 'first_name', 'last_name', 'email', 'date_of_birth', 'grade']
