from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.utils import timezone
from .forms import BudgetRequestForm, ExpenditureForm, InvoiceForm, VendorForm, AssetForm, RecurringExpenseForm
from .models import BudgetRequest, Expenditure, Invoice, Vendor, Asset, RecurringExpense


# ---------------------------
# Budget Request Views
# ---------------------------

@login_required
@permission_required('finance.add_budgetrequest', raise_exception=True)
def submit_budget_request(request):
    """
    View to submit a new budget request.
    
    If the request is POST, process the submitted form. If valid, save the request 
    associating it with the current user and redirect to the budget request list.
    If GET, render the form for a new budget request.
    """
    if request.method == 'POST':
        form = BudgetRequestForm(request.POST)
        if form.is_valid():
            budget_request = form.save(commit=False)
            # Associate the budget request with the current user.
            budget_request.requested_by = request.user
            budget_request.save()
            messages.success(request, 'Budget request submitted.')
            return redirect('finance:budget_request_list')
    else:
        form = BudgetRequestForm()
    return render(request, 'finance/budget_request_form.html', {'form': form})


@login_required
def budget_request_list(request):
    """
    View to display budget requests categorized by their status:
    Pending, Approved, and Declined.
    """
    pending_requests = BudgetRequest.objects.filter(status='PENDING')
    approved_requests = BudgetRequest.objects.filter(status='APPROVED')
    declined_requests = BudgetRequest.objects.filter(status='REJECTED')

    context = {
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'declined_requests': declined_requests,
        'pending_count': pending_requests.count(),
        'approved_count': approved_requests.count(),
        'declined_count': declined_requests.count(),
    }
    return render(request, 'finance/budget_request_list.html', context)

@login_required
def my_budget_request_list(request):
    """
    Display the current user's budget requests in three tabs (Pending, Approved, Declined)
    without the CRUD functionalities (read-only view).
    """
    # Filter the budget requests to only those created by the current user
    user_requests = BudgetRequest.objects.filter(requested_by=request.user)
    
    # Split requests by their status
    pending_requests = user_requests.filter(status='PENDING')
    approved_requests = user_requests.filter(status='APPROVED')
    declined_requests = user_requests.filter(status='REJECTED')

    context = {
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'declined_requests': declined_requests,
        'pending_count': pending_requests.count(),
        'approved_count': approved_requests.count(),
        'declined_count': declined_requests.count(),
        'read_only': True,  # Flag to hide CRUD functionalities in the template
    }
    return render(request, 'finance/budget_request_list.html', context)




@login_required
def budget_request_detail(request, pk):
    """
    View to display the details of a single budget request.
    
    Retrieves a BudgetRequest by primary key (pk) or returns a 404 error if not found.
    Renders the details in the 'budget_request_detail.html' template.
    """
    budget_request = get_object_or_404(BudgetRequest, pk=pk)
    return render(request, 'finance/budget_request_detail.html', {'budget_request': budget_request})


@login_required
@permission_required('finance.approve_budget_request', raise_exception=True)
def approve_budget_request(request, pk):
    """
    View to approve a budget request.
    
    Retrieves the BudgetRequest by pk, sets its status to APPROVED, records the 
    processing time and user, and then saves the changes.
    """
    budget_request = get_object_or_404(BudgetRequest, pk=pk)
    budget_request.status = 'APPROVED'
    budget_request.date_processed = timezone.now()
    budget_request.processed_by = request.user
    budget_request.save()
    messages.success(request, 'Budget request approved.')
    return redirect('finance:budget_request_list')


@login_required
@permission_required('finance.approve_budget_request', raise_exception=True)
def reject_budget_request(request, pk):
    """
    View to reject a budget request.
    
    Retrieves the BudgetRequest by pk, sets its status to REJECTED, records the 
    processing time and user, and then saves the changes.
    """
    budget_request = get_object_or_404(BudgetRequest, pk=pk)
    budget_request.status = 'REJECTED'
    budget_request.date_processed = timezone.now()
    budget_request.processed_by = request.user
    budget_request.save()
    messages.warning(request, 'Budget request rejected.')
    return redirect('finance:budget_request_list')


# ---------------------------
# Expenditure Views
# ---------------------------
@login_required
def expenditure_list(request):
    """
    View to list all expenditures.
    
    Retrieves all Expenditure objects and renders them in the 'expenditure_list.html' template.
    """
    expenditures = Expenditure.objects.all()
    return render(request, 'finance/expenditure_list.html', {'expenditures': expenditures})


@login_required
@permission_required('finance.add_expenditure', raise_exception=True)
def add_expenditure(request):
    """
    View to add a new expenditure.
    
    If the request is POST, processes the submitted form, associates the expenditure 
    with the current user, and saves it. If GET, renders an empty form.
    """
    if request.method == 'POST':
        form = ExpenditureForm(request.POST)
        if form.is_valid():
            expenditure = form.save(commit=False)
            # Record the current user as the one who recorded the expenditure.
            expenditure.recorded_by = request.user
            expenditure.save()
            messages.success(request, 'Expenditure recorded successfully.')
            return redirect('finance:expenditure_list')
    else:
        form = ExpenditureForm()
    return render(request, 'finance/expenditure_form.html', {'form': form})


@login_required
def expenditure_detail(request, pk):
    """
    Display the details of a specific expenditure.
    
    Retrieves the Expenditure object using the provided primary key (pk).
    If the expenditure does not exist, a 404 error is raised.
    Renders the details in the 'finance/expenditure_detail.html' template.
    """
    expenditure_request = get_object_or_404(Expenditure, pk=pk)
    return render(request, 'finance/expenditure_detail.html', {'expenditure_request': expenditure_request})


@login_required
@permission_required('finance.change_expenditure', raise_exception=True)
def update_expenditure(request, pk):
    """
    View to update an existing expenditure.
    
    Retrieves the expenditure by pk. If the request is POST, processes the submitted form
    with changes; if valid, saves the changes and redirects to the expenditure list.
    If GET, renders a form pre-populated with the expenditure data.
    """
    expenditure = get_object_or_404(Expenditure, pk=pk)
    if request.method == 'POST':
        form = ExpenditureForm(request.POST, instance=expenditure)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expenditure updated successfully.')
            return redirect('finance:expenditure_list')
    else:
        form = ExpenditureForm(instance=expenditure)
    return render(request, 'finance/expenditure_form.html', {'form': form})


@login_required
@permission_required('finance.delete_expenditure', raise_exception=True)
def delete_expenditure(request, pk):
    """
    View to delete an expenditure.
    
    Retrieves the expenditure by pk. On POST, deletes the expenditure and redirects
    to the expenditure list. If GET, renders a confirmation page.
    """
    expenditure = get_object_or_404(Expenditure, pk=pk)
    if request.method == 'POST':
        expenditure.delete()
        messages.success(request, 'Expenditure deleted successfully.')
        return redirect('finance:expenditure_list')
    return render(request, 'finance/delete_expenditure.html', {'expenditure': expenditure})


# ---------------------------
# Invoice Views
# ---------------------------

@login_required
def invoice_list(request):
    """
    View to list all invoices.
    
    Retrieves all Invoice objects and renders them in the 'invoice_list.html' template.
    """
    invoices = Invoice.objects.all()
    return render(request, 'finance/invoice_list.html', {'invoices': invoices})


@login_required
@permission_required('finance.add_invoice', raise_exception=True)
def add_invoice(request):
    """
    View to add a new invoice.
    
    If the request is POST, processes the submitted form (including file uploads),
    saves the invoice, and redirects to the invoice list. If GET, renders an empty form.
    """
    if request.method == 'POST':
        form = InvoiceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Invoice added successfully.')
            return redirect('finance:invoice_list')
    else:
        form = InvoiceForm()
    return render(request, 'finance/invoice_form.html', {'form': form})


@login_required
@permission_required('finance.change_invoice', raise_exception=True)
def update_invoice(request, pk):
    """
    View to update an existing invoice.
    
    Retrieves the invoice by pk. If the request is POST, processes the submitted form 
    with changes; if valid, saves the changes and redirects to the invoice list. 
    If GET, renders a form pre-populated with the invoice data.
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        form = InvoiceForm(request.POST, request.FILES, instance=invoice)
        if form.is_valid():
            form.save()
            messages.success(request, 'Invoice updated successfully.')
            return redirect('finance:invoice_list')
    else:
        form = InvoiceForm(instance=invoice)
    return render(request, 'finance/invoice_form.html', {'form': form})


@login_required
@permission_required('finance.delete_invoice', raise_exception=True)
def delete_invoice(request, pk):
    """
    View to delete an invoice.
    
    Retrieves the invoice by pk, deletes it, and then redirects to the invoice list.
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    invoice.delete()
    messages.success(request, 'Invoice deleted successfully.')
    return redirect('finance:invoice_list')


# ---------------------------
# Vendor Views
# ---------------------------

@login_required
def vendor_list(request):
    """
    View to list all vendors.
    
    Retrieves all Vendor objects and renders them in the 'vendor_list.html' template.
    """
    vendors = Vendor.objects.all()
    return render(request, 'finance/vendor_list.html', {'vendors': vendors})


@login_required
@permission_required('finance.add_vendor', raise_exception=True)
def add_vendor(request):
    """
    View to add a new vendor.
    
    If the request is POST, processes the submitted form (including file uploads), 
    saves the vendor, and redirects to the vendor list. If GET, renders an empty form.
    """
    if request.method == 'POST':
        form = VendorForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vendor added successfully.')
            return redirect('finance:vendor_list')
    else:
        form = VendorForm()
    return render(request, 'finance/vendor_form.html', {'form': form})


@login_required
@permission_required('finance.change_vendor', raise_exception=True)
def update_vendor(request, pk):
    """
    View to update an existing vendor.
    
    Retrieves the vendor by pk. If the request is POST, processes the submitted form 
    with changes; if valid, saves the changes and redirects to the vendor list. 
    If GET, renders a form pre-populated with the vendor data.
    """
    vendor = get_object_or_404(Vendor, pk=pk)
    if request.method == 'POST':
        form = VendorForm(request.POST, request.FILES, instance=vendor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vendor updated successfully.')
            return redirect('finance:vendor_list')
    else:
        form = VendorForm(instance=vendor)
    return render(request, 'finance/vendor_form.html', {'form': form})


@login_required
@permission_required('finance.delete_vendor', raise_exception=True)
def delete_vendor(request, pk):
    """
    View to delete a vendor.
    
    Retrieves the vendor by pk, deletes it, and then redirects to the vendor list.
    """
    vendor = get_object_or_404(Vendor, pk=pk)
    vendor.delete()
    messages.success(request, 'Vendor deleted successfully.')
    return redirect('finance:vendor_list')


# ---------------------------
# Asset Views
# ---------------------------

@login_required
def asset_list(request):
    """
    View to list all assets.
    
    Retrieves all Asset objects and renders them in the 'asset_list.html' template.
    """
    assets = Asset.objects.all()
    return render(request, 'finance/asset_list.html', {'assets': assets})


@login_required
@permission_required('finance.add_asset', raise_exception=True)
def add_asset(request):
    """
    View to add a new asset.
    
    If the request is POST, processes the submitted form, saves the asset, 
    and redirects to the asset list. If GET, renders an empty form.
    """
    if request.method == 'POST':
        form = AssetForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Asset added successfully.')
            return redirect('finance:asset_list')
    else:
        form = AssetForm()
    return render(request, 'finance/asset_form.html', {'form': form})


@login_required
@permission_required('finance.change_asset', raise_exception=True)
def update_asset(request, pk):
    """
    View to update an existing asset.
    
    Retrieves the asset by pk. If the request is POST, processes the submitted form 
    with changes; if valid, saves the changes and redirects to the asset list. 
    If GET, renders a form pre-populated with the asset data.
    """
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == 'POST':
        form = AssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, 'Asset updated successfully.')
            return redirect('finance:asset_list')
    else:
        form = AssetForm(instance=asset)
    return render(request, 'finance/asset_form.html', {'form': form})


@login_required
@permission_required('finance.delete_asset', raise_exception=True)
def delete_asset(request, pk):
    """
    View to delete an asset.
    
    Retrieves the asset by pk, deletes it, and then redirects to the asset list.
    """
    asset = get_object_or_404(Asset, pk=pk)
    asset.delete()
    messages.success(request, 'Asset deleted successfully.')
    return redirect('finance:asset_list')

@login_required
@permission_required('finance.view_company_assets', raise_exception=True)
def company_asset_list(request):
    """
    View to list all company assets for finance department or head staffers.
    
    Retrieves all Asset objects—covering assets entered by employees as well as 
    company-wide assets—and renders them in the 'finance/company_asset_list.html' template.
    Full CRUD functionality is available in this view for authorized staff.
    """
    assets = Asset.objects.all()
    return render(request, 'finance/company_asset_list.html', {'assets': assets})



# ---------------------------
# Recurring Expense Views
# ---------------------------

@login_required
def recurring_expense_list(request):
    """
    View to list all recurring expenses.
    
    Retrieves all RecurringExpense objects and renders them in the 
    'recurring_expense_list.html' template.
    """
    recurring_expenses = RecurringExpense.objects.all()
    return render(request, 'finance/recurring_expense_list.html', {'recurring_expenses': recurring_expenses})


@login_required
@permission_required('finance.add_recurringexpense', raise_exception=True)
def add_recurring_expense(request):
    """
    View to add a new recurring expense.
    
    If the request is POST, processes the submitted form, associates the expense 
    with the current user as the creator, and saves it. If GET, renders an empty form.
    """
    if request.method == 'POST':
        form = RecurringExpenseForm(request.POST)
        if form.is_valid():
            recurring_expense = form.save(commit=False)
            recurring_expense.created_by = request.user
            recurring_expense.save()
            messages.success(request, 'Recurring expense added successfully.')
            return redirect('finance:recurring_expense_list')
    else:
        form = RecurringExpenseForm()
    return render(request, 'finance/recurring_expense_form.html', {'form': form})
