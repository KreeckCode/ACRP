from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.core.mail import send_mail
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from .models import Provider, ProviderDocument
from .forms  import ProviderForm, ProviderDocumentForm

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
    qs = Provider.objects.all()
    return render(request, 'provider/provider_list.html', {'providers': qs})

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

# Document upload & review

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
        notes  = request.POST.get('review_notes')
        doc.status       = status
        doc.review_notes = notes
        doc.reviewed_by  = request.user
        doc.reviewed_at  = timezone.now()
        doc.save()

        # send rejection email in production
        if status == 'REJECTED' and not settings.DEBUG:
            send_mail(
                subject=f"[ACRP] Your document '{doc.name}' was rejected",
                message=(
                    f"Dear {doc.provider.trade_name},\n\n"
                    f"Your document '{doc.name}' has been marked REJECTED.\n\n"
                    f"Notes: {notes}\n\n"
                    "Please re-upload a valid document.\n\nRegards,\nACRP Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[doc.provider.email],
                fail_silently=False,
            )

        messages.success(request, 'Document review saved.')
        return redirect('provider:provider_detail', pk=doc.provider.pk)

    return render(request, 'provider/document_review.html', {'doc': doc})
