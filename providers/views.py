from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
from django.http import Http404
from django.contrib.auth import get_user_model
from .models import Provider, ApplicationLink
from .forms import ApplicationLinkForm
from .models import (
    Provider, ProviderAccreditation,
    Qualification, QualificationModule,
    ProviderUserProfile, AssessorProfile,
    ProviderDocument
)
from .forms import (
    ProviderForm, AccreditationForm,
    QualificationForm, ModuleForm,
    ProviderUserForm, AssessorForm,
    ProviderDocumentForm
)

User = get_user_model()


@login_required
def dashboard(request):
    """
    Role-based dashboard:
      - GLOBAL_SDP: overview of all providers
      - PROVIDER_ADMIN: this provider’s summary
      - INTERNAL_FACILITATOR: pending docs
    """
    role = request.user.acrp_role
    if role == User.ACRPRole.GLOBAL_SDP:
        total    = Provider.objects.count()
        recent   = Provider.objects.order_by('-created_at')[:5]
        return render(request, 'provider/dashboard_global.html', {
            'total': total, 'recent': recent
        })

    # provider-specific
    try:
        pup = request.user.provideruserprofile
    except ProviderUserProfile.DoesNotExist:
        messages.error(request, "You’re not assigned to any provider.")
        raise Http404()

    prov = pup.provider

    if role == User.ACRPRole.PROVIDER_ADMIN:
        return render(request, 'provider/dashboard_admin.html', {
            'provider': prov,
            'accreditations': prov.accreditations.all(),
            'qualifications': prov.qualifications.all(),
        })

    if role == User.ACRPRole.INTERNAL_FACILITATOR:
        pending_docs = prov.documents.filter(status='PENDING')
        return render(request, 'provider/dashboard_facilitator.html', {
            'provider': prov, 'pending_docs': pending_docs
        })

    messages.error(request, "No dashboard for your role.")
    raise Http404()


# — Provider CRUD — #

@login_required
@permission_required('provider.add_provider', raise_exception=True)
def provider_create(request):
    form = ProviderForm(request.POST or None)
    if form.is_valid():
        prov = form.save(commit=False)
        prov.created_by = request.user
        prov.updated_by = request.user
        prov.save()
        messages.success(request, 'Provider created.')
        return redirect('provider:provider_list')
    return render(request, 'provider/provider_form.html', {'form': form})

@login_required
@permission_required('provider.view_provider', raise_exception=True)
def provider_list(request):
    providers = Provider.objects.all()
    return render(request, 'provider/provider_list.html', {'providers': providers})

@login_required
@permission_required('provider.view_provider', raise_exception=True)
def provider_detail(request, pk):
    prov = get_object_or_404(Provider, pk=pk)
    return render(request, 'provider/provider_detail.html', {'provider': prov})

@login_required
@permission_required('provider.change_provider', raise_exception=True)
def provider_update(request, pk):
    prov = get_object_or_404(Provider, pk=pk)
    form = ProviderForm(request.POST or None, instance=prov)
    if form.is_valid():
        prov = form.save(commit=False)
        prov.updated_by = request.user
        prov.save()
        messages.success(request, 'Provider updated.')
        return redirect('provider:provider_detail', pk=pk)
    return render(request, 'provider/provider_form.html', {'form': form, 'update': True})

@login_required
@permission_required('provider.delete_provider', raise_exception=True)
def provider_delete(request, pk):
    prov = get_object_or_404(Provider, pk=pk)
    if request.method == 'POST':
        prov.delete()
        messages.success(request, 'Provider deleted.')
        return redirect('provider:provider_list')
    return render(request, 'provider/provider_confirm_delete.html', {'provider': prov})


# — Accreditation CRUD — #

@login_required
@permission_required('provider.add_provideraccreditation', raise_exception=True)
def accreditation_create(request, provider_pk):
    prov = get_object_or_404(Provider, pk=provider_pk)
    form = AccreditationForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        acc = form.save(commit=False)
        acc.provider = prov
        acc.save()
        messages.success(request, 'Accreditation added.')
        return redirect('provider:provider_detail', pk=provider_pk)
    return render(request, 'provider/accreditation_form.html', {'form': form, 'provider': prov})

@login_required
@permission_required('provider.change_provideraccreditation', raise_exception=True)
def accreditation_update(request, provider_pk, pk):
    acc  = get_object_or_404(ProviderAccreditation, pk=pk, provider_id=provider_pk)
    form = AccreditationForm(request.POST or None, request.FILES or None, instance=acc)
    if form.is_valid():
        form.save()
        messages.success(request, 'Accreditation updated.')
        return redirect('provider:provider_detail', pk=provider_pk)
    return render(request, 'provider/accreditation_form.html', {'form': form, 'provider': acc.provider})

@login_required
@permission_required('provider.delete_provideraccreditation', raise_exception=True)
def accreditation_delete(request, provider_pk, pk):
    acc = get_object_or_404(ProviderAccreditation, pk=pk, provider_id=provider_pk)
    if request.method == 'POST':
        acc.delete()
        messages.success(request, 'Accreditation removed.')
        return redirect('provider:provider_detail', pk=provider_pk)
    return render(request, 'provider/accreditation_confirm_delete.html', {'accreditation': acc})


# — Qualification CRUD — #

@login_required
@permission_required('provider.add_qualification', raise_exception=True)
def qualification_create(request, provider_pk):
    prov = get_object_or_404(Provider, pk=provider_pk)
    form = QualificationForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        q = form.save(commit=False)
        q.provider = prov
        q.save()
        messages.success(request, 'Qualification added.')
        return redirect('provider:provider_detail', pk=provider_pk)
    return render(request, 'provider/qualification_form.html', {'form': form, 'provider': prov})

@login_required
@permission_required('provider.view_qualification', raise_exception=True)
def qualification_detail(request, pk):
    q = get_object_or_404(Qualification, pk=pk)
    return render(request, 'provider/qualification_detail.html', {'qualification': q})

@login_required
@permission_required('provider.change_qualification', raise_exception=True)
def qualification_update(request, pk):
    q = get_object_or_404(Qualification, pk=pk)
    form = QualificationForm(request.POST or None, request.FILES or None, instance=q)
    if form.is_valid():
        form.save()
        messages.success(request, 'Qualification updated.')
        return redirect('provider:qualification_detail', pk=pk)
    return render(request, 'provider/qualification_form.html', {'form': form, 'update': True})

@login_required
@permission_required('provider.delete_qualification', raise_exception=True)
def qualification_delete(request, pk):
    q = get_object_or_404(Qualification, pk=pk)
    if request.method == 'POST':
        provider_pk = q.provider.pk
        q.delete()
        messages.success(request, 'Qualification removed.')
        return redirect('provider:provider_detail', pk=provider_pk)
    return render(request, 'provider/qualification_confirm_delete.html', {'qualification': q})


# — Module CRUD — #

@login_required
@permission_required('provider.add_qualificationmodule', raise_exception=True)
def module_create(request, qualification_pk):
    qual = get_object_or_404(Qualification, pk=qualification_pk)
    form = ModuleForm(request.POST or None, instance=QualificationModule(qualification=qual))
    if form.is_valid():
        m = form.save()
        messages.success(request, 'Module added.')
        return redirect('provider:qualification_detail', pk=qualification_pk)
    return render(request, 'provider/module_form.html', {'form': form, 'qualification': qual})

@login_required
@permission_required('provider.change_qualificationmodule', raise_exception=True)
def module_update(request, pk):
    mod = get_object_or_404(QualificationModule, pk=pk)
    form = ModuleForm(request.POST or None, instance=mod)
    if form.is_valid():
        form.save()
        messages.success(request, 'Module updated.')
        return redirect('provider:qualification_detail', pk=mod.qualification.pk)
    return render(request, 'provider/module_form.html', {'form': form, 'update': True, 'qualification': mod.qualification})

@login_required
@permission_required('provider.delete_qualificationmodule', raise_exception=True)
def module_delete(request, pk):
    mod = get_object_or_404(QualificationModule, pk=pk)
    if request.method == 'POST':
        qual_pk = mod.qualification.pk
        mod.delete()
        messages.success(request, 'Module removed.')
        return redirect('provider:qualification_detail', pk=qual_pk)
    return render(request, 'provider/module_confirm_delete.html', {'module': mod})


# — ProviderUserProfile CRUD — #

@login_required
@permission_required('provider.view_provideruserprofile', raise_exception=True)
def provider_user_list(request, provider_pk):
    prov = get_object_or_404(Provider, pk=provider_pk)
    users = prov.users.all()
    return render(request, 'provider/provider_user_list.html', {'users': users, 'provider': prov})

@login_required
@permission_required('provider.add_provideruserprofile', raise_exception=True)
def provider_user_create(request, provider_pk):
    prov = get_object_or_404(Provider, pk=provider_pk)
    form = ProviderUserForm(request.POST or None)
    if form.is_valid():
        pup = form.save(commit=False)
        pup.provider = prov
        pup.save()
        messages.success(request, 'Provider user added.')
        return redirect('provider:provider_user_list', provider_pk=provider_pk)
    return render(request, 'provider/provider_user_form.html', {'form': form, 'provider': prov})

@login_required
@permission_required('provider.change_provideruserprofile', raise_exception=True)
def provider_user_update(request, provider_pk, pk):
    pup = get_object_or_404(ProviderUserProfile, pk=pk, provider_id=provider_pk)
    form = ProviderUserForm(request.POST or None, instance=pup)
    if form.is_valid():
        form.save()
        messages.success(request, 'Provider user updated.')
        return redirect('provider:provider_user_list', provider_pk=provider_pk)
    return render(request, 'provider/provider_user_form.html', {'form': form, 'update': True, 'provider': pup.provider})

@login_required
@permission_required('provider.delete_provideruserprofile', raise_exception=True)
def provider_user_delete(request, provider_pk, pk):
    pup = get_object_or_404(ProviderUserProfile, pk=pk, provider_id=provider_pk)
    if request.method == 'POST':
        pup.delete()
        messages.success(request, 'Provider user removed.')
        return redirect('provider:provider_user_list', provider_pk=provider_pk)
    return render(request, 'provider/provider_user_confirm_delete.html', {'provider_user': pup})


# — AssessorProfile CRUD — #

@login_required
@permission_required('provider.view_assessorprofile', raise_exception=True)
def assessor_list(request, provider_pk):
    prov      = get_object_or_404(Provider, pk=provider_pk)
    assessors = prov.assessors.all()
    return render(request, 'provider/assessor_list.html', {'assessors': assessors, 'provider': prov})

@login_required
@permission_required('provider.add_assessorprofile', raise_exception=True)
def assessor_create(request, provider_pk):
    prov = get_object_or_404(Provider, pk=provider_pk)
    form = AssessorForm(request.POST or None)
    if form.is_valid():
        ap = form.save(commit=False)
        ap.provider = prov
        ap.save()
        messages.success(request, 'Assessor added.')
        return redirect('provider:assessor_list', provider_pk=provider_pk)
    return render(request, 'provider/assessor_form.html', {'form': form, 'provider': prov})

@login_required
@permission_required('provider.change_assessorprofile', raise_exception=True)
def assessor_update(request, provider_pk, pk):
    ap   = get_object_or_404(AssessorProfile, pk=pk, provider_id=provider_pk)
    form = AssessorForm(request.POST or None, instance=ap)
    if form.is_valid():
        form.save()
        messages.success(request, 'Assessor updated.')
        return redirect('provider:assessor_list', provider_pk=provider_pk)
    return render(request, 'provider/assessor_form.html', {'form': form, 'update': True, 'provider': ap.provider})

@login_required
@permission_required('provider.delete_assessorprofile', raise_exception=True)
def assessor_delete(request, provider_pk, pk):
    ap = get_object_or_404(AssessorProfile, pk=pk, provider_id=provider_pk)
    if request.method == 'POST':
        ap.delete()
        messages.success(request, 'Assessor removed.')
        return redirect('provider:assessor_list', provider_pk=provider_pk)
    return render(request, 'provider/assessor_confirm_delete.html', {'assessor': ap})


# — Document upload & review — #

@login_required
@permission_required('provider.add_providerdocument', raise_exception=True)
def document_upload(request, provider_pk):
    prov = get_object_or_404(Provider, pk=provider_pk)
    form = ProviderDocumentForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        doc = form.save(commit=False)
        doc.provider = prov
        doc.save()
        messages.success(request, 'Document uploaded; pending review.')
        return redirect('provider:provider_detail', pk=provider_pk)
    return render(request, 'provider/document_form.html', {'form': form, 'provider': prov})

@login_required
@permission_required('provider.change_providerdocument', raise_exception=True)
def document_review(request, doc_pk):
    doc = get_object_or_404(ProviderDocument, pk=doc_pk)
    if request.method == 'POST':
        status = request.POST.get('status')
        notes  = request.POST.get('review_notes', '')
        doc.status       = status
        doc.reviewed_by  = request.user
        doc.reviewed_at  = timezone.now()
        doc.review_notes = notes
        doc.save()

        if status == 'REJECTED' and not settings.DEBUG:
            try:
                send_mail(
                    subject=f"[ACRP] Your document '{doc.name}' was rejected",
                    message=(
                        f"Dear {doc.provider.trade_name},\n\n"
                        f"Your document '{doc.name}' was marked REJECTED.\n"
                        f"Notes: {notes}\n\n"
                        "Please re-upload a valid document.\n\nRegards,\nACRP Team"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[doc.provider.email],
                )
            except Exception as e:
                messages.error(request, f"Email send failed: {e}")

        messages.success(request, 'Document review saved.')
        return redirect('provider:provider_detail', pk=doc.provider.pk)

    return render(request, 'provider/document_review.html', {'doc': doc})



@login_required
@permission_required('providers.view_applicationlink', raise_exception=True)
def link_list(request):
    # assume provider_profile exists on user
    provider = request.user.provider_profile.provider
    links = provider.application_links.all()
    return render(request, 'providers/link_list.html', {'links': links})

@login_required
@permission_required('providers.add_applicationlink', raise_exception=True)
def link_create(request):
    if request.method == 'POST':
        form = ApplicationLinkForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            link.provider   = request.user.provider_profile.provider
            link.created_by = request.user
            link.save()
            messages.success(request, 'Application link created.')
            return redirect('providers:link_list')
    else:
        form = ApplicationLinkForm()
    return render(request, 'providers/link_form.html', {'form': form})

@login_required
@permission_required('providers.change_applicationlink', raise_exception=True)
def link_update(request, pk):
    provider = request.user.provider_profile.provider
    link = get_object_or_404(ApplicationLink, pk=pk, provider=provider)
    if request.method == 'POST':
        form = ApplicationLinkForm(request.POST, instance=link)
        if form.is_valid():
            form.save()
            messages.success(request, 'Link updated.')
            return redirect('providers:link_list')
    else:
        form = ApplicationLinkForm(instance=link)
    return render(request, 'providers/link_form.html', {'form': form, 'update': True})
