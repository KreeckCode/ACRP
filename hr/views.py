from django.utils import timezone
from django.forms import ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden, HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import (
    EmployeeProfile,
    EmployeeDocument,
    EmployeeWarning,
    HRDocumentStorage,
    DocumentAccessLog,
    LeaveBalance,
    Payslip,
    LeaveRequest,
    LeaveType,
)
from .forms import (
    EmployeeProfileForm,
    EmployeeDocumentForm,
    EmployeeWarningForm,
    HRDocumentStorageForm,
    PayslipForm,
    LeaveRequestForm,
)

from django.db.models import Sum  



from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from hr.models import EmployeeProfile, EmployeeDocument, EmployeeWarning, LeaveRequest, Payslip

@login_required
def my_profile(request):
    """
    Displays the logged-in user's profile, including employee-related data.
    """
    user = request.user
    try:
        profile = user.employee_profile
    except EmployeeProfile.DoesNotExist:
        profile = None
        

    documents = EmployeeDocument.objects.filter(employee=profile)
    warnings = profile.warnings.all() if profile else []
    leave_requests = LeaveRequest.objects.filter(employee=profile)
    payslips = Payslip.objects.filter(employee=profile)

    context = {
        "user": user,
        "profile": profile,
        "documents": documents,
        "warnings": warnings,
        "leave_requests": leave_requests,
        "payslips": payslips,
    }
    return render(request, "hr/profile.html", context)



# Helper function to check if the user is HR staff
def is_hr_staff(user):
    """
    Checks if the user belongs to the HR group.
    """
    return user.groups.filter(name="HR").exists()



from django.db.models import Q
from django.shortcuts import render
from hr.models import EmployeeProfile

def employee_profile_list(request):
    """
    View to list all employee profiles, with optional search & department filtering.
    """
    # 1. Base queryset
    profiles = EmployeeProfile.objects.select_related('user').all()

    # 2. Read the GET parameters
    search_query = request.GET.get('search', '').strip()
    department_filter = request.GET.get('department', '').strip()

    # 3. Apply SEARCH if provided
    if search_query:
        # Example: Search across first_name, last_name, email, job_title
        profiles = profiles.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(job_title__icontains=search_query)
        )

    # 4. Apply DEPARTMENT filter if provided (assuming it's a string in EmployeeProfile.department)
    if department_filter:
        profiles = profiles.filter(department=department_filter)

    # 5. Render
    context = {
        "profiles": profiles,
        "search_query": search_query,
        "department_filter": department_filter,
        "departments": Department.objects.all(),  # or distinct department names
    }

    return render(request, "hr/employee_profile_list.html", context)


# Employee Profile Views


@login_required
def employee_profile_list(request):
    """
    View to list all employee profiles for HR staff.
    """
    profiles = EmployeeProfile.objects.all()
    return render(request, "hr/employee_profile_list.html", {"profiles": profiles})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from accounts.models import Department, User
from hr.models import EmployeeProfile
from hr.forms import EmployeeProfileUserForm

@login_required
def create_employee_profile(request):
    """
    Single view that creates both User and EmployeeProfile in one go
    using the integrated EmployeeProfileUserForm.
    """
    if request.method == 'POST':
        form = EmployeeProfileUserForm(request.POST)
        if form.is_valid():
            form.save()  # Creates new user & employee profile
            messages.success(request, "Employee profile (and user) created successfully.")
            return redirect("employee_profile_list")  # Make sure this URL exists!
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = EmployeeProfileUserForm()  # Blank form for a new EmployeeProfile & User

    return render(request, "hr/employee_profile_form.html", {
        'create_view': True,
        'form': form, 
    })


@login_required
def update_employee_profile(request, profile_id):
    """
    Updates both the User and the EmployeeProfile in one go,
    using the same integrated form.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    user = profile.user  # The related user

    if request.method == 'POST':
        form = EmployeeProfileUserForm(
            request.POST,
            user_instance=user,
            profile_instance=profile
        )
        if form.is_valid():
            form.save()  # Updates existing user & profile
            messages.success(request, "Employee profile updated successfully.")
            return redirect("employee_profile_list")  # Make sure this URL exists!
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Pre-fill form with existing data
        form = EmployeeProfileUserForm(
            user_instance=user,
            profile_instance=profile
        )

    return render(request, "hr/employee_profile_form.html", {
        'form': form,
    })


# Employee Document Views


@login_required
#@user_passes_test(is_hr_staff)
def manage_employee_document(request, profile_id, document_id=None):
    """
    View to create or edit an employee document.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    document = (
        get_object_or_404(EmployeeDocument, id=document_id) if document_id else None
    )

    if request.method == "POST":
        form = EmployeeDocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            document = form.save(commit=False)
            document.employee = profile
            document.save()
            messages.success(request, "Document saved successfully.")
            return redirect("employee_profile_list")
        else:
            messages.error(request, "Error saving document. Please check the form.")
    else:
        form = EmployeeDocumentForm(instance=document)

    return render(
        request, "hr/employee_document_form.html", {"form": form, "profile": profile}
)



# Employee Warning Views

@login_required
def employee_warning_list(request, profile_id):
    """
    Displays a list of all warnings for a specific employee.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    warnings = EmployeeWarning.objects.filter(employee=profile)

    return render(request, "hr/employee_warning_list.html", {
        "profile": profile,
        "warnings": warnings,
    })

@login_required
def employee_warning_detail(request, profile_id, warning_id):
    """
    Displays details of a specific warning.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    warning = get_object_or_404(EmployeeWarning, id=warning_id, employee=profile)
    return render(request, "hr/employee_warning_detail.html", {"profile": profile, "warning": warning})



@login_required
def create_employee_warning(request):
    """
    Creates a new warning for an employee, allowing employee selection from a dropdown.
    """
    if request.method == "POST":
        form = EmployeeWarningForm(request.POST, request.FILES)
        if form.is_valid():
            warning = form.save()
            messages.success(request, "Warning created successfully.")
            return redirect("employee_warning_list", profile_id=warning.employee.id)
    else:
        form = EmployeeWarningForm()

    employees = EmployeeProfile.objects.all()  # Fetch employees for dropdown

    return render(request, "hr/employee_warning_form.html", {"form": form, "employees": employees})

@login_required
def edit_employee_warning(request, profile_id, warning_id):
    """
    Updates an existing warning for an employee.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    warning = get_object_or_404(EmployeeWarning, id=warning_id, employee=profile)

    if request.method == "POST":
        form = EmployeeWarningForm(request.POST, request.FILES, instance=warning)
        if form.is_valid():
            form.save()
            messages.success(request, "Warning updated successfully.")
            return redirect("employee_warning_list", profile_id=warning.employee.id)
    else:
        form = EmployeeWarningForm(instance=warning)

    return render(request, "hr/employee_warning_form.html", {"form": form, "profile": profile})

@login_required
def all_employee_warnings(request):
    """
    Displays a list of all warnings issued to employees.
    """
    warnings = EmployeeWarning.objects.select_related("employee__user").all()  # Optimized query
    return render(request, "hr/all_employee_warnings.html", {"warnings": warnings})


@login_required
def delete_employee_warning(request, profile_id, warning_id):
    """
    Deletes a warning for an employee.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    warning = get_object_or_404(EmployeeWarning, id=warning_id, employee=profile)

    if request.method == "POST":
        warning.delete()
        messages.success(request, "Warning deleted successfully.")
        return redirect("employee_warning_list", profile_id=profile.id)

    return render(request, "hr/employee_warning_confirm_delete.html", {"profile": profile, "warning": warning})

@login_required
def employee_profile_detail(request, profile_id):
    """
    Displays employee profile details including warnings.
    """
    profile = get_object_or_404(EmployeeProfile, id=profile_id)
    warnings = profile.warnings.all()  # Fetch all warnings for this employee
    return render(request, 'hr/employee_profile_detail.html', {
        'profile': profile,
        'warnings': warnings,
        'detail_view': True,
    })



import os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from .models import (
    HRDocumentStorage,
    DocumentFolder,
    DocumentAccessLog,
    DocumentShare
)
from .forms import (
    HRDocumentStorageForm,
    DocumentFolderForm,
    DocumentShareForm
)

@login_required
def manage_hr_document(request, document_id=None):
    """
    View to create or edit an HR document.
    If 'document_id' is provided, we're editing an existing document.
    Otherwise, we're creating a new one.
    """
    document = get_object_or_404(HRDocumentStorage, id=document_id) if document_id else None

    if request.method == "POST":
        form = HRDocumentStorageForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            saved_doc = form.save()
            messages.success(request, "HR Document saved successfully.")
            # After saving, redirect to your document list or folder detail
            return redirect("hr_document_list")  # or wherever you'd like to go
        else:
            messages.error(request, "Error saving HR document. Please check the form.")
    else:
        form = HRDocumentStorageForm(instance=document)

    return render(request, "hr/hr_document_form.html", {
        "form": form,
        "document": document,
    })


@login_required
def folder_list(request):
    """
    Shows all top-level folders (where parent is None) and
    any root documents (folder=None).
    """
    folders = DocumentFolder.objects.filter(parent__isnull=True)
    documents = HRDocumentStorage.objects.filter(folder__isnull=True).order_by('-date_uploaded')
    return render(request, "hr/folder_list.html", {
        "folders": folders,
        "documents": documents,
    })


@login_required
def folder_detail(request, folder_id):
    """
    Shows the contents of a specific folder:
    - subfolders
    - documents
    """
    folder = get_object_or_404(DocumentFolder, id=folder_id)
    subfolders = folder.subfolders.all().order_by('name')
    documents = folder.documents.all().order_by('-date_uploaded')
    return render(request, "hr/folder_detail.html", {
        "folder": folder,
        "subfolders": subfolders,
        "documents": documents,
    })


@login_required
def create_folder(request, parent_id=None):
    """
    Creates a new folder. If 'parent_id' is provided, sets that as the parent folder.
    """
    parent_folder = None
    if parent_id:
        parent_folder = get_object_or_404(DocumentFolder, id=parent_id)

    if request.method == 'POST':
        form = DocumentFolderForm(request.POST)
        if form.is_valid():
            new_folder = form.save(commit=False)
            new_folder.owner = request.user
            if parent_folder:
                new_folder.parent = parent_folder
            new_folder.save()
            messages.success(request, "Folder created successfully.")
            # Redirect to the parent folder detail, or folder list if no parent
            if parent_folder:
                return redirect("folder_detail", folder_id=parent_folder.id)
            else:
                return redirect("folder_list")
        else:
            messages.error(request, "Error creating folder. Please check the form.")
    else:
        form = DocumentFolderForm()
        # Pre-set the parent if specified
        if parent_folder:
            form.fields['parent'].initial = parent_folder.id

    return render(request, "hr/create_folder.html", {
        "form": form,
        "parent_folder": parent_folder,
    })

@login_required
def folder_delete(request, folder_id):
    folder = get_object_or_404(DocumentFolder, id=folder_id)

    if request.method == 'POST':
        folder.delete()
        messages.success(request, 'Folder Deleted successfully')
        return redirect('folder_list')
    
    return render(request, 'hr/confirm_delete.html', {'folder':folder})



@login_required
def upload_document(request, folder_id=None):
    """
    Uploads a new document into the specified folder (if any).
    """
    folder = None
    if folder_id:
        folder = get_object_or_404(DocumentFolder, id=folder_id)

    if request.method == "POST":
        form = HRDocumentStorageForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            # Assign chosen folder
            if folder:
                doc.folder = folder
            doc.save()
            messages.success(request, "Document uploaded successfully.")
            if folder:
                return redirect("folder_detail", folder_id=folder.id)
            else:
                return redirect("folder_list")
        else:
            messages.error(request, "Error uploading document. Please check the form.")
    else:
        form = HRDocumentStorageForm()
        # If we're in a folder, pre-set
        if folder:
            form.fields['folder'].initial = folder.id

    return render(request, "hr/upload_document.html", {
        "form": form,
        "folder": folder,
    })


@login_required
def document_download(request, document_id):
    """
    Download a document file directly, logging the access.
    """
    document = get_object_or_404(HRDocumentStorage, id=document_id)

    # Log the access
    DocumentAccessLog.objects.create(
        document=document,
        accessed_by=request.user
    )

    # Provide the file for download
    file_path = document.file.path
    if not os.path.exists(file_path):
        raise Http404("File not found.")

    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=document.file.name)
    return response

@login_required
def document_delete(request, document_id):
    document = get_object_or_404(HRDocumentStorage, id=document_id)

    if request.method == 'POST':
        document.delete()
        messages.success(request, 'Document Successfully Deleted')
        return redirect('hr:folder_list')
    return render(request, 'hr/confirm_delete.html')


@login_required
def document_access_logs(request, document_id):
    """
    View to list access logs for a specific HR document.
    """
    document = get_object_or_404(HRDocumentStorage, id=document_id)
    access_logs = DocumentAccessLog.objects.filter(document=document).order_by('-access_date')
    return render(
        request,
        "hr/document_access_logs.html",
        {"document": document, "access_logs": access_logs},
    )


@login_required
def share_document(request, document_id):
    """
    Create or manage a share link for the specified document.
    """
    document = get_object_or_404(HRDocumentStorage, id=document_id)

    # Either get existing share or create new
    share_obj, created = DocumentShare.objects.get_or_create(document=document)
    if request.method == 'POST':
        form = DocumentShareForm(request.POST, instance=share_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Share link updated.")
            return redirect("folder_list")
        else:
            messages.error(request, "Error updating share link.")
    else:
        form = DocumentShareForm(instance=share_obj)

    # Generate the share URL
    share_url = share_obj.get_share_url(request=request)

    return render(request, "hr/share_document.html", {
        "document": document,
        "form": form,
        "share_url": share_url,
        "share_obj": share_obj,
    })

def document_share_download(request, token):
    """
    Download a shared document using a share token.
    """
    share_obj = get_object_or_404(DocumentShare, token=token, is_active=True)
    # Check expiration
    if share_obj.is_expired():
        return render(request, "hr/share_expired.html", {})

    document = share_obj.document

    # Optionally log access if the learner is authenticated
    if request.user.is_authenticated:
        DocumentAccessLog.objects.create(document=document, accessed_by=request.user)

    # Provide the file for download
    file_path = document.file.path
    if not os.path.exists(file_path):
        raise Http404("File not found.")

    response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=document.file.name)
    return response



def document_share_view(request, token):
    """
    Public or semi-public view for accessing a shared document
    by token (UUID).
    """
    share_obj = get_object_or_404(DocumentShare, token=token, is_active=True)
    # Check expiration
    if share_obj.is_expired():
        return render(request, "hr/share_expired.html", {})

    document = share_obj.document

    # Optional: If you want to track access from non-logged-in users, 
    if request.user.is_authenticated:
        # Log access
        DocumentAccessLog.objects.create(document=document, accessed_by=request.user)

    return render(request, "hr/share_view.html", {
        "document": document,
        "share_obj": share_obj,
    })

from .forms import ExternalAttachForm
from .models import DocumentRequest
@login_required
def external_document_request_view(request, token):
    """
    Allows external recipients to attach the requested document via a unique URL.
    """
    doc_req = get_object_or_404(DocumentRequest, external_token=token, request_type='external')
    if request.method == 'POST':
        form = ExternalAttachForm(request.POST, request.FILES, document_request=doc_req, instance=doc_req)
        if form.is_valid():
            doc_req = form.save(commit=False)
            doc_req.response_date = timezone.now()
            doc_req.status = 'completed'
            doc_req.save()
            messages.success(request, "Document attached successfully.")
            return redirect('external_document_request_success')
        else:
            messages.error(request, "Error attaching document. Please check the form.")
    else:
        form = ExternalAttachForm(document_request=doc_req, instance=doc_req)
    return render(request, 'hr/external_document_request.html', {'form': form, 'doc_req': doc_req})

def external_document_request_success(request):
    """
    A simple success page after an external recipient attaches a document.
    """
    return render(request, 'hr/external_document_request_success.html')

from .forms import RequestDocumentForm, ApproveDocumentRequestForm
from .models import DocumentRequest

@login_required
def create_document_request(request):
    """
    Allows an employee to create a document request.
    For internal requests, the employee can search for the intended recipient.
    For external requests, the form prompts for external contact details.
    """
    if request.method == 'POST':
        form = RequestDocumentForm(request.POST)
        if form.is_valid():
            doc_req = form.save(commit=False)
            doc_req.requested_by = request.user
            doc_req.request_date = timezone.now()
            # Additional validation: if internal, recipient must be set.
            if doc_req.request_type == 'internal' and not doc_req.recipient:
                form.add_error('recipient', 'For internal requests, please select a recipient.')
                return render(request, 'hr/request_document.html', {'form': form})
            # For external requests, require at least external recipient email.
            if doc_req.request_type == 'external' and not doc_req.external_recipient_email:
                form.add_error('external_recipient_email', 'For external requests, please provide the email address.')
                return render(request, 'hr/request_document.html', {'form': form})
            doc_req.save()
            messages.success(request, "Document request submitted successfully.")
            return redirect('document_request_list')
        else:
            messages.error(request, "There was an error submitting your request. Please check the form.")
    else:
        form = RequestDocumentForm()
    return render(request, 'hr/request_document.html', {'form': form})

@login_required
def document_request_list(request):
    """
    Lists all document requests made by the employee, as well as those they need to process.
    """
    # Requests created by the user
    my_requests = DocumentRequest.objects.filter(requested_by=request.user).order_by('-request_date')
    # For internal requests: those where the user is the recipient
    incoming_requests = DocumentRequest.objects.filter(recipient=request.user, status='pending').order_by('request_date')
    return render(request, 'hr/document_request_list.html', {
        'my_requests': my_requests,
        'incoming_requests': incoming_requests,
    })

@login_required
def document_request_detail(request, request_id):
    """
    Shows details of a specific document request.
    """
    doc_req = get_object_or_404(DocumentRequest, id=request_id)
    # If the request type is external, compute the external URL here
    external_url = None
    if doc_req.request_type == 'external':
        external_url = doc_req.get_external_request_url(request)
    return render(request, 'hr/document_request_detail.html', {
        'doc_req': doc_req,
        'external_url': external_url,
    })


@login_required
def process_document_request(request, request_id):
    """
    Allows the recipient to approve or reject a document request and attach the requested file if approved.
    Only the designated recipient can process the request.
    """
    doc_req = get_object_or_404(DocumentRequest, id=request_id, recipient=request.user)
    if request.method == 'POST':
        form = ApproveDocumentRequestForm(request.POST, request.FILES, instance=doc_req)
        if form.is_valid():
            doc_req = form.save(commit=False)
            doc_req.response_date = timezone.now()
            # If the request is approved and a file is attached, mark it as completed.
            if doc_req.status == 'approved' and doc_req.attached_file:
                doc_req.status = 'completed'
            form.save()
            messages.success(request, "Your response has been submitted.")
            return redirect('document_request_list')
        else:
            messages.error(request, "Error processing the request. Please check the form.")
    else:
        form = ApproveDocumentRequestForm(instance=doc_req)
    return render(request, 'hr/process_document_request.html', {
        'form': form,
        'doc_req': doc_req,
    })

@login_required
def delete_document_request(request, request_id):
    """
    Allows the owner of the request to delete it if it is still pending.
    """
    doc_req = get_object_or_404(DocumentRequest, id=request_id, requested_by=request.user)
    if request.method == 'POST':
        doc_req.delete()
        messages.success(request, "Document request deleted successfully.")
        return redirect('document_request_list')
    return render(request, 'hr/confirm_delete_request.html', {'doc_req': doc_req})











# Leave Request Views

@login_required
#@user_passes_test(is_hr_staff)
def leave_request_list(request):
    """
    View to list all leave requests.
    """
    leave_requests = LeaveRequest.objects.all()
    return render(
        request, "hr/leave_request_list.html", {"leave_requests": leave_requests}
    )


@login_required
#@user_passes_test(is_hr_staff)
def handle_leave_request(request, leave_request_id):
    """
    View to approve or decline a leave request.
    """
    leave_request = get_object_or_404(LeaveRequest, id=leave_request_id)
    if request.method == "POST":
        if "approve" in request.POST:
            leave_request.approve(hr_comment="Leave approved.")
            messages.success(request, "Leave request approved.")
        elif "decline" in request.POST:
            leave_request.decline(hr_comment="Leave declined.")
            messages.warning(request, "Leave request declined.")
        return redirect("leave_request_list")

    return render(
        request, "hr/leave_request_handle.html", {"leave_request": leave_request}
    )


@login_required
def create_leave_request(request):
    """
    View for employees to create a new leave request.
    """
    if not hasattr(request.user, 'employee_profile'):
        messages.error(request, "You do not have an employee profile to request leave.")
        return redirect('leave_request_list')

    profile = request.user.employee_profile  # Get the employee profile

    if request.method == "POST":
        # Pass the employee to the form
        form = LeaveRequestForm(request.POST, employee=profile)
        if form.is_valid():
            # Save the form with the employee set
            leave_request = form.save(commit=False)
            leave_request.employee = profile  # Assign the employee
            leave_request.status = "PENDING"  # Default status
            leave_request.save()
            messages.success(request, "Your leave request has been successfully submitted.")
            return redirect('leave_request_list')
        else:
            messages.error(request, "There was an error with your leave request. Please correct the errors below.")
    else:
        form = LeaveRequestForm(employee=profile)

    # Include leave balance in the context for display
    leave_balance = profile.leave_balance if hasattr(profile, 'leave_balance') else None

    return render(request, "hr/leave_request_form.html", {
        "form": form,
        "leave_balance": leave_balance,
    })



@login_required
#@user_passes_test(is_hr_staff)
def leave_analytics_dashboard(request):
    """
    View to display leave analytics for HR staff.
    """
    total_leave_requests = LeaveRequest.objects.count()
    approved_leaves = LeaveRequest.objects.filter(status='APPROVED').count()
    pending_leaves = LeaveRequest.objects.filter(status='PENDING').count()
    department_leave_data = (
        EmployeeProfile.objects.values('department')
        .annotate(total_allocated=Sum('leave_balance__total_leave_days'),
                  remaining=Sum('leave_balance__leave_days_remaining'))
        .order_by('department')
    )
    return render(request, 'hr/leave_analytics_dashboard.html', {
        'total_leave_requests': total_leave_requests,
        'approved_leaves': approved_leaves,
        'pending_leaves': pending_leaves,
        'department_leave_data': department_leave_data,
    })

def approve(self, hr_comment=None):
    """
    Approve the leave request and adjust the employee's leave balance.
    """
    if self.status == 'PENDING':
        leave_balance = self.employee.leave_balance
        if leave_balance.leave_days_remaining >= self.total_days:
            self.status = 'APPROVED'
            self.hr_comment = hr_comment
            leave_balance.leave_days_remaining -= self.total_days
            leave_balance.save()
            self.save()
        else:
            raise ValidationError(f"Insufficient leave balance. Only {leave_balance.leave_days_remaining} days remaining.")


@login_required
def payslip_list(request):
    """
    View to list all payslips for the logged-in employee.
    """
    try:
        # Retrieve payslips for the employee
        payslips = Payslip.objects.filter(employee=request.user.employee_profile)
    except AttributeError:
        # Handle case where the user does not have an associated employee profile
        payslips = []
    return render(request, 'hr/payslip_list.html', {'payslips': payslips})

@login_required
def view_payslip(request, payslip_id):
    """
    View to display detailed information about a specific payslip for the logged-in employee.
    """
    # Retrieve the payslip for the logged-in employee
    payslip = get_object_or_404(Payslip, id=payslip_id, employee=request.user.employee_profile)
    return render(request, 'hr/view_payslip.html', {'payslip': payslip})



@login_required
def hr_document_list(request):
    """
    View to list all HR documents for HR staff.
    Supports optional search/filter for section, etc.
    """
    docs = HRDocumentStorage.objects.all()

    # Prepare a set or a list of section choices (code, label)
    # Usually stored in HRDocumentStorage.SECTION_CATEGORIES
    SECTION_CHOICES = HRDocumentStorage.SECTION_CATEGORIES

    # Handle GET params
    search_query = request.GET.get('search', '').strip()
    section_filter = request.GET.get('section', '').strip()

    if search_query:
        docs = docs.filter(title__icontains=search_query)
    if section_filter:
        docs = docs.filter(section=section_filter)

    context = {
        'documents': docs,
        'sections': SECTION_CHOICES,  # <-- pass the section choices to the template
        'search_query': search_query,
        'section_filter': section_filter,
    }

    return render(request, 'hr/hr_document_list.html', context)


@login_required
def delete_hr_document(request, document_id):
    """
    View to delete an HR document from the database.
    """
    document = get_object_or_404(HRDocumentStorage, id=document_id)

    if request.method == "POST":
        document.delete()
        messages.success(request, "Document deleted successfully.")
        return redirect("folder_list")
    else:
        # Optional: show a confirmation page
        return render(request, "hr/confirm_document_delete.html", {"document": document})
