from django.urls import path
from .views import (
    SignatureRequestCreateView, SignatureRequestListView,
    sign_document_view, signature_signed_confirmation
)

urlpatterns = [
    path('requests/create/', SignatureRequestCreateView.as_view(), name='signature_request_create'),
    path('requests/', SignatureRequestListView.as_view(), name='signature_request_list'),
    # The signer will receive a unique link (with signer_id) to sign the document:
    path('sign/<int:signer_id>/', sign_document_view, name='sign_document'),
    path('signed/confirmation/', signature_signed_confirmation, name='signature_signed_confirmation'),
]
