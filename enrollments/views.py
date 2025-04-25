from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseForbidden

from .models import AssociatedAffiliation, DesignatedAffiliation, StudentAffiliation
from .forms import (
    AssociatedForm, DesignatedForm, StudentForm,
    AssocDocFormSet, DesigDocFormSet, StudentDocFormSet
)
from accounts.models import User

# Only GLOBAL_SDP or PROVIDER_ADMIN may approve :contentReference[oaicite:5]{index=5}
def is_admin(user):
    return user.acrp_role in {
        User.ACRPRole.GLOBAL_SDP,
        User.ACRPRole.PROVIDER_ADMIN
    }

# Generic list view with search
def _list(request, model, template, search_fields):
    qs = model.objects.all()
    q  = request.GET.get('search', '').strip()
    if q:
        query = Q()
        for f in search_fields:
            query |= Q(**{f+"__icontains": q})
        qs = qs.filter(query)
    return render(request, template, {'objects': qs, 'search_query': q})

@login_required
@permission_required('enrollments.view_associatedaffiliation', raise_exception=True)
def associated_list(request):
    return _list(request, AssociatedAffiliation, "enrollments/associated_list.html",
                 ['full_names','surname','email'])

@login_required
@permission_required('enrollments.view_designatedaffiliation', raise_exception=True)
def designated_list(request):
    return _list(request, DesignatedAffiliation, "enrollments/designated_list.html",
                 ['full_names','email'])

@login_required
@permission_required('enrollments.view_studentaffiliation', raise_exception=True)
def student_list(request):
    return _list(request, StudentAffiliation, "enrollments/student_list.html",
                 ['full_names','email'])

# Generic create/update handler
def _crud(request, pk, model, form_class, formset_class, list_url, form_template):
    instance = get_object_or_404(model, pk=pk) if pk else None
    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        fs   = formset_class(request.POST, request.FILES, instance=instance)
        if form.is_valid() and fs.is_valid():
            obj = form.save()
            fs.instance = obj
            fs.save()
            messages.success(request, "Saved successfully.")
            return redirect(list_url)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = form_class(instance=instance)
        fs   = formset_class(instance=instance)
    return render(request, form_template, {'form': form, 'formset': fs})

# Associated CRUD
@login_required
@permission_required('enrollments.add_associatedaffiliation', raise_exception=True)
def associated_create(request):
    return _crud(request, None, AssociatedAffiliation, AssociatedForm, AssocDocFormSet,
                 'enrollments:associated_list', "enrollments/associated_form.html")

@login_required
@permission_required('enrollments.change_associatedaffiliation', raise_exception=True)
def associated_update(request, pk):
    return _crud(request, pk, AssociatedAffiliation, AssociatedForm, AssocDocFormSet,
                 'enrollments:associated_list', "enrollments/associated_form.html")

# Designated CRUD
@login_required
@permission_required('enrollments.add_designatedaffiliation', raise_exception=True)
def designated_create(request):
    return _crud(request, None, DesignatedAffiliation, DesignatedForm, DesigDocFormSet,
                 'enrollments:designated_list', "enrollments/designated_form.html")

@login_required
@permission_required('enrollments.change_designatedaffiliation', raise_exception=True)
def designated_update(request, pk):
    return _crud(request, pk, DesignatedAffiliation, DesignatedForm, DesigDocFormSet,
                 'enrollments:designated_list', "enrollments/designated_form.html")

# Student CRUD
@login_required
@permission_required('enrollments.add_studentaffiliation', raise_exception=True)
def student_create(request):
    return _crud(request, None, StudentAffiliation, StudentForm, StudentDocFormSet,
                 'enrollments:student_list', "enrollments/student_form.html")

@login_required
@permission_required('enrollments.change_studentaffiliation', raise_exception=True)
def student_update(request, pk):
    return _crud(request, pk, StudentAffiliation, StudentForm, StudentDocFormSet,
                 'enrollments:student_list', "enrollments/student_form.html")

# Single delete confirmation for all three models
@login_required
@permission_required('enrollments.delete_associatedaffiliation', raise_exception=True)
def application_delete(request, model_name, pk):
    model_map = {
        'associated': AssociatedAffiliation,
        'designated': DesignatedAffiliation,
        'student':    StudentAffiliation
    }
    model = model_map.get(model_name)
    if not model:
        return HttpResponseForbidden("Invalid application type.")
    obj = get_object_or_404(model, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, "Deleted successfully.")
        return redirect(f'enrollments:{model_name}_list')
    return render(request, "enrollments/application_confirm_delete.html", {'object': obj})

# Approval views
@login_required
@user_passes_test(is_admin, login_url='/', redirect_field_name=None)
def associated_approve(request, pk):
    obj = get_object_or_404(AssociatedAffiliation, pk=pk)
    obj.approved = True; obj.save()
    messages.success(request, "Associated application approved.")
    return redirect('enrollments:associated_list')

@login_required
@user_passes_test(is_admin, login_url='/', redirect_field_name=None)
def designated_approve(request, pk):
    obj = get_object_or_404(DesignatedAffiliation, pk=pk)
    obj.approved = True; obj.save()
    messages.success(request, "Designated application approved.")
    return redirect('enrollments:designated_list')

@login_required
@user_passes_test(is_admin, login_url='/', redirect_field_name=None)
def student_approve(request, pk):
    obj = get_object_or_404(StudentAffiliation, pk=pk)
    obj.approved = True; obj.save()
    messages.success(request, "Student application approved.")
    return redirect('enrollments:student_list')
