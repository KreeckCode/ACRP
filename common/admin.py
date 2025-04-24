from django.contrib import admin
from .models import SignatureRequest, Signer, SignatureDocument

class SignatureDocumentInline(admin.TabularInline):
    model = SignatureDocument
    extra = 1  # Allows adding multiple documents within SignatureRequest

class SignerInline(admin.TabularInline):
    model = Signer
    extra = 1

@admin.register(SignatureRequest)
class SignatureRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'creator', 'status', 'expiration', 'created_at')
    list_filter = ('status', 'expiration', 'created_at')
    search_fields = ('title', 'description', 'creator__email')
    inlines = [SignerInline, SignatureDocumentInline]
    ordering = ('-created_at',)

@admin.register(SignatureDocument)
class SignatureDocumentAdmin(admin.ModelAdmin):
    list_display = ('request', 'file', 'uploaded_at')
    search_fields = ('request__title',)

@admin.register(Signer)
class SignerAdmin(admin.ModelAdmin):
    list_display = ('email', 'request', 'order', 'signed_at')
    list_filter = ('signed_at',)
    search_fields = ('email', 'request__title')

