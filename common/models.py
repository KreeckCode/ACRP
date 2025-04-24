from django.db import models
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from datetime import timedelta

class SignatureRequest(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('completed', 'Completed'),
        ('expired', 'Expired')
    ]
    creator = models.ForeignKey(User, on_delete=models.PROTECT)
    title = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expiration = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    def __str__(self):
        return f"{self.title} - {self.status}"

class SignatureDocument(models.Model):
    request = models.ForeignKey(SignatureRequest, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='signature_docs/')
    # You may calculate and store a SHA-256 hash for file integrity
    hash = models.CharField(max_length=64, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document for {self.request.title}"

class Signer(models.Model):
    request = models.ForeignKey(
        SignatureRequest, 
        on_delete=models.CASCADE, 
        related_name='signers'
    )
    email = models.EmailField()
    order = models.PositiveIntegerField(help_text="Signing order")
    signature = models.TextField(blank=True, help_text="Base64-encoded signature image")
    signed_at = models.DateTimeField(null=True, blank=True)
    
    # Log interactions as a list of dicts
    access_log = models.JSONField(default=list, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('request', 'email')  # Prevent duplicate signers for the same request
        ordering = ['order']  # Ensure signers are always retrieved in order

    def add_log(self, action, ip, user_agent):
        """Helper to add an audit log entry with better concurrency handling"""
        self.refresh_from_db(fields=['access_log'])  # Prevent concurrent write issues
        log_entry = {
            'action': action,
            'timestamp': timezone.now().isoformat(),
            'ip': ip,
            'user_agent': user_agent,
        }
        self.access_log.append(log_entry)
        self.save(update_fields=['access_log'])  # Only update the access log field

    def get_signing_link(self):
        """Returns the URL for a signer to sign the document."""
        return reverse('sign_document_view', kwargs={'signer_id': self.id})
     
    def __str__(self):
        return f"Signer {self.email} for {self.request.title} (Order: {self.order})"
