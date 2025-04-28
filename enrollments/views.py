from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseForbidden

from .models import AssociatedAffiliation
from .forms import (
    AssociatedForm,
    AssocDocFormSet
)
from accounts.models import User


def onboarding(request):
    """
    Let a brand-new visitor choose how they want to join:
      • Associated Affiliation
      • Student (via invitation link)
      • Provider
    """
    if request.method == 'POST':
        choice = request.POST.get('registration_type')
        if choice == 'associated':
            return redirect('enrollments:associated_create')
        elif choice == 'student':
            return redirect('enrollments:learner_apply_prompt')
        elif choice == 'provider':
            # you need to create a provider_self_register view or adjust this URL
            return redirect('providers:provider_self_register')
        messages.error(request, "Please select one of the options above.")
    return render(request, 'enrollments/onboarding.html')


def learner_apply_prompt(request):
    """
    Simple form asking the applicant to paste their application link token,
    then redirecting them to the real student apply page.
    """
    if request.method == 'POST':
        token = request.POST.get('token','').strip()
        if token:
            return redirect(reverse('student:learner_apply', args=[token]))
        messages.error(request, "Please enter your registration link token.")
    return render(request, 'enrollments/learner_apply_prompt.html')

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
#@login_required
#@permission_required('enrollments.add_associatedaffiliation', raise_exception=True)
def associated_create(request):
    return _crud(request, None, AssociatedAffiliation, AssociatedForm, AssocDocFormSet,
                 'enrollments:associated_list', "enrollments/associated_form.html")

@login_required
@permission_required('enrollments.change_associatedaffiliation', raise_exception=True)
def associated_update(request, pk):
    return _crud(request, pk, AssociatedAffiliation, AssociatedForm, AssocDocFormSet,
                 'enrollments:associated_list', "enrollments/associated_form.html")


# Single delete confirmation for all three models
@login_required
@permission_required('enrollments.delete_associatedaffiliation', raise_exception=True)
def application_delete(request, model_name, pk):
    model_map = {
        'associated': AssociatedAffiliation,
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
