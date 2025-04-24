from datetime import timedelta
from django import forms
from .models import EmployeeProfile, EmployeeDocument, EmployeeWarning, HRDocumentStorage, Payslip, LeaveBalance, LeaveRequest, LeaveType
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from datetime import timedelta
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit
from .models import DocumentRequest 


class EmployeeProfileForm(forms.ModelForm):
    """
    Form to create or edit an Employee Profile.
    """
    class Meta:
        model = EmployeeProfile
        fields = ['user', 'department', 'job_title', 'date_of_hire', 'date_of_termination', 'manager', 'emergency_contact', 'emergency_contact_phone', 'active']
        widgets = {
            'date_of_hire': forms.DateInput(attrs={'type': 'date'}),
            'date_of_termination': forms.DateInput(attrs={'type': 'date'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_date_of_termination(self):
        """
        Ensure that termination date is not before hire date.
        """
        termination_date = self.cleaned_data.get('date_of_termination')
        hire_date = self.cleaned_data.get('date_of_hire')

        if termination_date and termination_date < hire_date:
            raise ValidationError("Termination date cannot be before the hire date.")
        return termination_date


class EmployeeDocumentForm(forms.ModelForm):
    """
    Form to create or update an Employee Document.
    """
    class Meta:
        model = EmployeeDocument
        fields = ['employee', 'document_type', 'title', 'file', 'uploaded_by', 'is_editable_by_employee', 'is_shared_with_employee', 'available_on_request']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'allow_multiple_selected': True}),
            'employee': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_file(self):
        """
        Ensure file size is below 10MB.
        """
        file = self.cleaned_data.get('file')
        if file and file.size > 10 * 1024 * 1024:  # 10MB limit
            raise ValidationError("File size must be less than 10MB.")
        return file


class EmployeeWarningForm(forms.ModelForm):
    """
    Form to create or update an Employee Warning.
    """
    class Meta:
        model = EmployeeWarning
        fields = ['employee', 'title', 'description', 'document', 'start_date', 'expiry_date', 'status']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'employee': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_expiry_date(self):
        """
        Ensure the expiry date is after the start date.
        """
        start_date = self.cleaned_data.get('start_date')
        expiry_date = self.cleaned_data.get('expiry_date')

        if expiry_date < start_date:
            raise ValidationError("Expiry date cannot be before the start date.")
        return expiry_date

from django import forms
from .models import HRDocumentStorage, DocumentFolder, DocumentShare

class HRDocumentStorageForm(forms.ModelForm):
    """
    Form to manage HR Document Storage.
    """
    class Meta:
        model = HRDocumentStorage
        fields = ['folder', 'section', 'title', 'file', 'expiry_date']

        widgets = {
            'file': forms.ClearableFileInput(attrs={'allow_multiple_selected': True}),
            'section': forms.Select(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            # 'folder': forms.Select(...) # automatically a dropdown
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        # if file and file.size > 10 * 1024 * 1024:
        #     raise forms.ValidationError("File size must be less than 10MB.")
        return file


class DocumentFolderForm(forms.ModelForm):
    """
    Creates or edits a folder in the nested structure.
    """
    class Meta:
        model = DocumentFolder
        fields = ['name', 'parent']


class DocumentShareForm(forms.ModelForm):
    """
    Form for creating or editing a share link.
    """
    class Meta:
        model = DocumentShare
        fields = ['expires_at', 'is_active']
        widgets = {
            'expires_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local',
                       'class':'form-control',
                       },
            ),
        }

class RequestDocumentForm(forms.ModelForm):
    # Override the field to accept a value in MB
    max_file_size = forms.FloatField(
        label="Maximum File Size (in MB)",
        initial=10,
        help_text="Set the maximum allowed file size (in MB) for the attachment."
    )

    class Meta:
        model = DocumentRequest
        fields = [
            'title', 
            'description', 
            'request_type',
            'recipient',  # Only applicable for internal requests
            'external_recipient_name',
            'external_recipient_email',
            'folder',
            'max_file_size',
        ]
        labels = {
            'title': 'Document Title',
            'description': 'Details / Reason',
            'request_type': 'Request Type',
            'recipient': 'Internal Recipient',
            'external_recipient_name': 'External Recipient Name',
            'external_recipient_email': 'External Recipient Email',
            'folder': 'Target Folder',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('title'),
            Field('description'),
            Field('request_type', css_class="request-type"),
            Div(
                Field('recipient'),
                css_id="internal-fields"
            ),
            Div(
                Field('external_recipient_name'),
                Field('external_recipient_email'),
                css_id="external-fields"
            ),
            Field('folder'),
            Field('max_file_size'),
            Submit('submit', 'Submit Request')
        )
        # Optional: Hide or adjust fields based on request type via JS later.
        self.fields['recipient'].required = False
        self.fields['external_recipient_name'].required = False
        self.fields['external_recipient_email'].required = False

    def clean_max_file_size(self):
        mb = self.cleaned_data.get('max_file_size')
        # Convert MB to bytes
        return int(mb * 1024 * 1024)
    


class ExternalAttachForm(forms.ModelForm):
    class Meta:
        model = DocumentRequest
        fields = ['attached_file']

    def __init__(self, *args, **kwargs):
        self.doc_req = kwargs.pop('document_request', None)
        super().__init__(*args, **kwargs)
        if self.doc_req:
            max_mb = self.doc_req.max_file_size / (1024 * 1024)
            self.fields['attached_file'].help_text = f"Maximum allowed file size: {max_mb:.2f} MB"

    def clean_attached_file(self):
        file = self.cleaned_data.get('attached_file')
        if file and self.doc_req and file.size > self.doc_req.max_file_size:
            max_mb = self.doc_req.max_file_size / (1024 * 1024)
            raise forms.ValidationError(f"File size exceeds the limit of {max_mb:.2f} MB.")
        return file







class PayslipForm(forms.ModelForm):
    """
    Form to manage an employee's payslip.
    """
    class Meta:
        model = Payslip
        fields = ['employee', 'month', 'basic_salary', 'deductions', 'bonuses', 'net_salary', 'document']
        widgets = {
            'month': forms.DateInput(attrs={'type': 'month'}),
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'document': forms.ClearableFileInput(attrs={'allow_multiple_selected': True}),
        }

    def clean_net_salary(self):
        """
        Ensure the net salary does not exceed the basic salary + bonuses.
        """
        basic_salary = self.cleaned_data.get('basic_salary')
        bonuses = self.cleaned_data.get('bonuses')
        net_salary = self.cleaned_data.get('net_salary')

        if net_salary > (basic_salary + bonuses):
            raise ValidationError("Net salary cannot exceed the basic salary plus bonuses.")
        return net_salary


class LeaveBalanceForm(forms.ModelForm):
    """
    Form to manage an employee's leave balance.
    """
    class Meta:
        model = LeaveBalance
        fields = ['employee', 'total_leave_days', 'leave_days_remaining', 'leave_cycle_start', 'leave_cycle_end']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'leave_cycle_start': forms.DateInput(attrs={'type': 'date'}),
            'leave_cycle_end': forms.DateInput(attrs={'type': 'date'}),
        }




class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.employee = kwargs.pop('employee', None)  # Retrieve the employee from kwargs
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        leave_type = cleaned_data.get('leave_type')

        if not self.employee:
            raise ValidationError("Employee is not set for this leave request.")

        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError("End date cannot be before start date.")

            # Calculate total weekdays
            current_date = start_date
            total_weekdays = 0
            while current_date <= end_date:
                if current_date.weekday() not in [5, 6]:  # Exclude weekends
                    total_weekdays += 1
                current_date += timedelta(days=1)

            # Check leave balance
            leave_balance = self.employee.leave_balance
            if leave_balance and leave_type:
                if total_weekdays > leave_balance.leave_days_remaining:
                    raise ValidationError(
                        f"You only have {leave_balance.leave_days_remaining} days remaining for {leave_type.name} leave."
                    )

            # Save the total weekdays as the `total_days` field
            cleaned_data['total_days'] = total_weekdays

        return cleaned_data

class LeaveTypeForm(forms.ModelForm):
    """
    Form to manage leave types.
    """
    class Meta:
        model = LeaveType
        fields = ['name', 'description', 'default_allocation']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# Formsets to handle multiple instances at once (for documents, warnings, etc.)

EmployeeDocumentFormSet = modelformset_factory(
    EmployeeDocument,
    form=EmployeeDocumentForm,
    extra=1,
    fields=('employee', 'document_type', 'title', 'file', 'uploaded_by', 'is_editable_by_employee', 'is_shared_with_employee', 'available_on_request')
)

EmployeeWarningFormSet = modelformset_factory(
    EmployeeWarning,
    form=EmployeeWarningForm,
    extra=1,
    fields=('employee', 'title', 'description', 'document', 'start_date', 'expiry_date', 'status')
)


from accounts.models import Department

class EmployeeProfileForm(forms.ModelForm):
    # Override department to be a dropdown from accounts.Department
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,  # or True
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = EmployeeProfile
        fields = [
            'user', 'department', 'job_title', 'date_of_hire',
            'date_of_termination', 'manager', 'emergency_contact',
            'emergency_contact_phone', 'active'
        ]
        widgets = {
            'date_of_hire': forms.DateInput(attrs={'type': 'date'}),
            'date_of_termination': forms.DateInput(attrs={'type': 'date'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
        }


from django import forms
from django.core.exceptions import ValidationError
from accounts.models import User, Department, Role
from hr.models import EmployeeProfile

class EmployeeProfileUserForm(forms.Form):
    """
    A single form that combines the necessary User fields and EmployeeProfile fields
    in order to create or update both objects at once.
    """

    # -- USER FIELDS --
    username = forms.CharField(
        max_length=150,
        required=True,
        help_text="Unique username for this user."
    )
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=60, required=False)
    employee_code = forms.CharField(
        max_length=30,
        required=True,
        help_text="Unique code for this employee."
    )

    # Allow picking a role from your Role model
    role = forms.ModelChoiceField(
        queryset=Role.objects.all(),
        required=False,
        help_text="Pick the user's role if needed."
    )

    # If you want the operator to set a password here:
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Set a password for this user (optional)."
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        label="Confirm Password"
    )

    # Department from the 'accounts.Department' model (FK on User)
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=True,
        help_text="Select a department for this user."
    )

    # -- EMPLOYEE PROFILE FIELDS --
    job_title = forms.CharField(max_length=100, required=True)
    date_of_hire = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True
    )
    date_of_termination = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False
    )
    emergency_contact = forms.CharField(max_length=100, required=False)
    emergency_contact_phone = forms.CharField(max_length=20, required=False)
    active = forms.BooleanField(initial=True, required=False)

    # Manager field to pick an existing EmployeeProfile as manager
    manager = forms.ModelChoiceField(
        queryset=EmployeeProfile.objects.all(),
        required=False,
        help_text="Select this employee's manager (if any)."
    )

    def __init__(self, *args, **kwargs):
        """
        Accept existing User and EmployeeProfile instances to edit them.
        """
        self.user_instance = kwargs.pop('user_instance', None)
        self.profile_instance = kwargs.pop('profile_instance', None)
        super().__init__(*args, **kwargs)

        # If editing existing data, fill initial values from the instances
        if self.user_instance:
            self.fields['username'].initial = self.user_instance.username
            self.fields['first_name'].initial = self.user_instance.first_name
            self.fields['last_name'].initial = self.user_instance.last_name
            self.fields['email'].initial = self.user_instance.email
            self.fields['phone'].initial = self.user_instance.phone
            self.fields['employee_code'].initial = self.user_instance.employee_code
            self.fields['role'].initial = self.user_instance.role
            if self.user_instance.department:
                self.fields['department'].initial = self.user_instance.department

        if self.profile_instance:
            self.fields['job_title'].initial = self.profile_instance.job_title
            self.fields['date_of_hire'].initial = self.profile_instance.date_of_hire
            self.fields['date_of_termination'].initial = self.profile_instance.date_of_termination
            self.fields['emergency_contact'].initial = self.profile_instance.emergency_contact
            self.fields['emergency_contact_phone'].initial = self.profile_instance.emergency_contact_phone
            self.fields['active'].initial = self.profile_instance.active
            if self.profile_instance.manager:
                self.fields['manager'].initial = self.profile_instance.manager.id

    # 1) Ensure username is unique if changed or new
    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if not self.user_instance or (self.user_instance and self.user_instance.username != username):
            if User.objects.filter(username__iexact=username).exists():
                raise ValidationError("That username is already in use. Please choose a different one.")
        return username

    # 2) Ensure email is unique if changed or new
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if not self.user_instance or (self.user_instance and self.user_instance.email.lower() != email):
            if User.objects.filter(email__iexact=email).exists():
                raise ValidationError("That email is already in use. Please choose a different one.")
        return email

    def clean(self):
        """
        Check date_of_termination >= date_of_hire and confirm password if provided.
        """
        cleaned_data = super().clean()

        # Date check
        date_of_hire = cleaned_data.get('date_of_hire')
        date_of_termination = cleaned_data.get('date_of_termination')
        if date_of_hire and date_of_termination and date_of_termination < date_of_hire:
            self.add_error('date_of_termination', "Termination date cannot be before hire date.")

        # Password confirmation check
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        if password or password_confirm:
            if password != password_confirm:
                self.add_error('password_confirm', "Passwords do not match.")

        return cleaned_data

    def save(self):
        """
        Create or update both User and EmployeeProfile in one go.
        """
        # If we're editing existing instances, use them; otherwise, create new ones
        user = self.user_instance if self.user_instance else User()
        profile = self.profile_instance if self.profile_instance else EmployeeProfile()

        # Update USER fields
        user.username = self.cleaned_data['username']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        user.employee_code = self.cleaned_data['employee_code']
        user.role = self.cleaned_data['role']  # <--- store selected role
        user.department = self.cleaned_data['department']

        # If a password is set in form, update it
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)

        user.save()

        # Update EMPLOYEE PROFILE fields
        profile.user = user
        # If EmployeeProfile.department is a CharField, store the department name:
        profile.department = user.department.name if user.department else ""
        #
        # If you have changed EmployeeProfile.department to a ForeignKey, do:
        # profile.department = user.department

        profile.job_title = self.cleaned_data['job_title']
        profile.date_of_hire = self.cleaned_data['date_of_hire']
        profile.date_of_termination = self.cleaned_data.get('date_of_termination')
        profile.emergency_contact = self.cleaned_data.get('emergency_contact', '')
        profile.emergency_contact_phone = self.cleaned_data.get('emergency_contact_phone', '')
        profile.active = self.cleaned_data['active']
        profile.manager = self.cleaned_data.get('manager', None)
        profile.save()

        return user, profile


from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Field, Div
from .models import DocumentRequest

class RequestDocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentRequest
        fields = [
            'title', 
            'description', 
            'request_type',
            'recipient',  # Only applicable for internal requests
            'external_recipient_name',
            'external_recipient_email',
            'folder'
        ]
        labels = {
            'title': 'Document Title',
            'description': 'Details / Reason',
            'request_type': 'Request Type',
            'recipient': 'Internal Recipient',
            'external_recipient_name': 'External Recipient Name',
            'external_recipient_email': 'External Recipient Email',
            'folder': 'Target Folder',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('title'),
            Field('description'),
            Field('request_type', css_class="request-type"),
            Div(
                Field('recipient'),
                css_id="internal-fields"
            ),
            Div(
                Field('external_recipient_name'),
                Field('external_recipient_email'),
                css_id="external-fields"
            ),
            Field('folder'),
            Submit('submit', 'Submit Request')
        )
        # By default, hide external fields if request type is internal
        self.fields['recipient'].required = False
        self.fields['external_recipient_name'].required = False
        self.fields['external_recipient_email'].required = False

class ApproveDocumentRequestForm(forms.ModelForm):
    class Meta:
        model = DocumentRequest
        fields = ['status', 'attached_file']
        labels = {
            'status': 'Approval Status',
            'attached_file': 'Attach Requested File',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', 'Submit Response'))
