from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import CreateView, ListView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from .models import SignatureRequest, SignatureDocument, Signer
from .forms import SignatureRequestForm, SignerForm
import hashlib

# View for creating a signature request with attachments.
class SignatureRequestCreateView(CreateView):
    model = SignatureRequest
    form_class = SignatureRequestForm
    template_name = 'common/signature_request_form.html'
    success_url = reverse_lazy('signature_request_list')

    def form_valid(self, form):
        form.instance.creator = self.request.user
        response = super().form_valid(form)
        request_obj = self.object
        files = self.request.FILES.getlist('documents')
        for f in files:
            f.seek(0)
            hash_value = hashlib.sha256(f.read()).hexdigest()
            SignatureDocument.objects.create(request=request_obj, file=f, hash=hash_value)
            f.seek(0)
        
        signing_link = request_obj.get_signing_link()

        messages.success(self.request, f"Signature request created. Share this link with signers: {signing_link}")
        
        return response


# View for listing signature requests (for the creator/ERP user).
class SignatureRequestListView(ListView):
    model = SignatureRequest
    template_name = 'common/signature_request_list.html'
    context_object_name = 'requests'
    paginate_by = 10

    def get_queryset(self):
        return SignatureRequest.objects.filter(creator=self.request.user).order_by('-created_at')

# View for a signer to view and sign a document.
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.contrib import messages
from .models import SignatureRequest, Signer
from .forms import SignerForm

def sign_document_view(request, request_id):
    signature_request = get_object_or_404(SignatureRequest, id=request_id)
    ip = request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    now = timezone.now()
    
    # Check if the request is expired
    if signature_request.status != 'completed' and now > signature_request.expiration:
        signature_request.status = 'expired'
        signature_request.save()
        messages.error(request, "This signature request has expired.")
        return render(request, 'common/signature_expired.html', {'signature_request': signature_request})

    # If the document is opened for the first time, update the status
    if signature_request.status == 'draft':
        signature_request.status = 'sent'
        signature_request.save()

    if request.method == 'POST':
        form = SignerForm(request.POST)
        if form.is_valid():
            signer = Signer.objects.create(
                request=signature_request,
                email=form.cleaned_data['email'],
                signature=form.cleaned_data['signature'],
                signed_at=timezone.now(),
                ip_address=ip,
                user_agent=user_agent
            )
            signer.add_log('signed', ip, user_agent)

            # If all signers have signed, mark as completed
            if all(s.signed_at for s in signature_request.signers.all()):
                signature_request.status = 'completed'
                signature_request.save()

            messages.success(request, "Document signed successfully.")
            return redirect('signature_signed_confirmation')
    else:
        form = SignerForm()

    documents = signature_request.documents.all()
    return render(request, 'common/sign_document.html', {
        'form': form,
        'signature_request': signature_request,
        'documents': documents,
    })

# A simple confirmation view after signing.
def signature_signed_confirmation(request):
    return render(request, 'common/signature_confirmation.html')
