# enrollments/admin.py - FIXED - Non-editable fields removed from fieldsets
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline, GenericStackedInline
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import CGMPAffiliation, CPSCAffiliation, CMTPAffiliation, Document, RegistrationSession


# === DOCUMENT INLINE ADMIN ===
class DocumentInline(GenericStackedInline):
    """
    Inline admin for documents - shows documents related to any affiliation
    """
    model = Document
    extra = 1  # Show 1 empty form by default
    max_num = 10  # Maximum 10 documents
    fields = ('category', 'file', 'description')
    readonly_fields = ('uploaded_at', 'uploaded_by', 'original_filename', 'file_size', 'mime_type')


# === CGMP AFFILIATION ADMIN ===
@admin.register(CGMPAffiliation)
class CGMPAffiliationAdmin(admin.ModelAdmin):
    """
    Professional admin interface for CGMP Affiliations
    """
    # Include the document inline
    inlines = [DocumentInline]
    
    # List display
    list_display = [
        'get_full_name', 'email', 'ordination_status', 'approved', 
        'document_count', 'created_at'
    ]
    
    # List filters
    list_filter = [
        'approved', 'ordination_status', 'involved_pastoral', 
        'registered_elsewhere', 'created_at', 'gender'
    ]
    
    # Search fields
    search_fields = [
        'first_name', 'last_name', 'email', 'id_number', 
        'congregation_name', 'denomination'
    ]
    
    # Fieldsets for organized display - FIXED: Removed non-editable fields
    fieldsets = (
        ('Personal Information', {
            'fields': (
                ('title', 'gender', 'initials'),
                ('first_name', 'last_name', 'preferred_name'),
                ('id_number', 'passport_number', 'date_of_birth'),
                ('race', 'disability'),
                ('home_language', 'other_languages'),
                'religious_affiliation',
            ),
            'classes': ('wide',),
        }),
        
        ('Contact Information', {
            'fields': (
                ('email', 'cell'),
                ('tel_work', 'tel_home', 'fax'),
                'website',
                'street_address',
                'postal_address',
                ('postal_code', 'province', 'country'),
            ),
            'classes': ('wide',),
        }),
        
        ('Education & Professional', {
            'fields': (
                ('highest_qualification', 'qualification_date'),
                'qualification_institution',
                'occupation',
                'work_description',
                ('years_ministry', 'months_ministry'),
            ),
            'classes': ('wide',),
        }),
        
        ('Ministry Information', {
            'fields': (
                ('ordination_status', 'ordination_date'),
                'ordaining_body',
                ('current_ministry_role', 'congregation_name'),
                'denomination',
                'involved_pastoral',
                'pastoral_responsibilities',
                'preaching_frequency',
                ('registered_elsewhere', 'continuing_education'),
                'other_registrations',
            ),
            'classes': ('wide',),
        }),
        
        ('Background Checks', {
            'fields': (
                'disciplinary_action',
                'disciplinary_description',
                'felony_conviction',
                'felony_description',
            ),
            'classes': ('wide',),
        }),
        
        ('Legal Agreements', {
            'fields': (
                'popi_act_accepted',
                'terms_accepted',
                'information_accurate',
            ),
            'classes': ('wide',),
        }),
    )
    
    # Readonly fields - FIXED: All non-editable fields here
    readonly_fields = [
        'created_at', 'updated_at', 'created_user', 
        'approved', 'approved_at', 'approved_by'
    ]
    
    # Custom methods for list display
    def get_full_name(self, obj):
        return obj.get_display_name()
    get_full_name.short_description = 'Name'
    get_full_name.admin_order_field = 'first_name'
    
    def document_count(self, obj):
        count = obj.documents.count()
        if count > 0:
            url = reverse('admin:enrollments_document_changelist')
            return format_html(
                '<a href="{}?content_type__model=cgmpaffiliation&object_id={}">{} docs</a>',
                url, obj.pk, count
            )
        return '0 docs'
    document_count.short_description = 'Documents'
    
    # Custom actions
    actions = ['approve_applications', 'reject_applications']
    
    def approve_applications(self, request, queryset):
        from django.utils import timezone
        for obj in queryset:
            obj.approved = True
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
            obj.save()
        self.message_user(request, f'{queryset.count()} applications approved.')
    approve_applications.short_description = 'Approve selected applications'
    
    def reject_applications(self, request, queryset):
        updated = queryset.update(approved=False, approved_by=None, approved_at=None)
        self.message_user(request, f'{updated} applications rejected.')
    reject_applications.short_description = 'Reject selected applications'


# === CPSC AFFILIATION ADMIN ===
@admin.register(CPSCAffiliation)
class CPSCAffiliationAdmin(admin.ModelAdmin):
    """
    Professional admin interface for CPSC Affiliations
    """
    inlines = [DocumentInline]
    
    list_display = [
        'get_full_name', 'email', 'counseling_certification', 
        'approved', 'document_count', 'created_at'
    ]
    
    list_filter = [
        'approved', 'counseling_certification', 'clinical_supervision',
        'professional_liability_insurance', 'created_at'
    ]
    
    search_fields = [
        'first_name', 'last_name', 'email', 'id_number',
        'certification_body', 'supervisor_name'
    ]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                ('title', 'gender', 'initials'),
                ('first_name', 'last_name', 'preferred_name'),
                ('id_number', 'passport_number', 'date_of_birth'),
                ('race', 'disability'),
                ('home_language', 'other_languages'),
                'religious_affiliation',
            ),
        }),
        
        ('Contact Information', {
            'fields': (
                ('email', 'cell'),
                ('tel_work', 'tel_home', 'fax'),
                'website',
                'street_address', 'postal_address',
                ('postal_code', 'province', 'country'),
            ),
        }),
        
        ('Education & Professional', {
            'fields': (
                ('highest_qualification', 'qualification_date'),
                'qualification_institution',
                'occupation',
                'work_description',
                ('years_ministry', 'months_ministry'),
            ),
        }),
        
        ('Background Checks', {
            'fields': (
                'disciplinary_action', 'disciplinary_description',
                'felony_conviction', 'felony_description',
            ),
        }),
        
        ('CPSC-Specific Information', {
            'fields': (
                ('counseling_certification', 'certification_body', 'certification_date'),
                ('trauma_training', 'grief_counseling_training'),
                ('addiction_counseling_training', 'family_counseling_training'),
                'counseling_practice_type',
                ('clinical_supervision', 'supervisor_name', 'supervision_hours'),
                'specialization_areas',
                ('professional_liability_insurance', 'insurance_provider'),
            ),
        }),
        
        ('Legal Agreements', {
            'fields': (
                'popi_act_accepted', 'terms_accepted', 'information_accurate',
            ),
        }),
    )
    
    readonly_fields = [
        'created_at', 'updated_at', 'created_user',
        'approved', 'approved_at', 'approved_by'
    ]
    
    def get_full_name(self, obj):
        return obj.get_display_name()
    get_full_name.short_description = 'Name'
    
    def document_count(self, obj):
        return obj.documents.count()
    document_count.short_description = 'Documents'


# === CMTP AFFILIATION ADMIN ===
@admin.register(CMTPAffiliation)
class CMTPAffiliationAdmin(admin.ModelAdmin):
    """
    Professional admin interface for CMTP Affiliations
    """
    inlines = [DocumentInline]
    
    list_display = [
        'get_full_name', 'email', 'institution_name', 'institution_type',
        'approved', 'document_count', 'created_at'
    ]
    
    list_filter = [
        'approved', 'institution_type', 'institution_accredited',
        'delivery_methods', 'curriculum_type', 'created_at'
    ]
    
    search_fields = [
        'first_name', 'last_name', 'email', 'id_number',
        'institution_name', 'teaching_subjects'
    ]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                ('title', 'gender', 'initials'),
                ('first_name', 'last_name', 'preferred_name'),
                ('id_number', 'passport_number', 'date_of_birth'),
                ('race', 'disability'),
                ('home_language', 'other_languages'),
                'religious_affiliation',
            ),
        }),
        
        ('Contact Information', {
            'fields': (
                ('email', 'cell'),
                ('tel_work', 'tel_home', 'fax'),
                'website',
                'street_address', 'postal_address',
                ('postal_code', 'province', 'country'),
            ),
        }),
        
        ('Education & Professional', {
            'fields': (
                ('highest_qualification', 'qualification_date'),
                'qualification_institution',
                'occupation',
                'work_description',
                ('years_ministry', 'months_ministry'),
            ),
        }),
        
        ('Background Checks', {
            'fields': (
                'disciplinary_action', 'disciplinary_description',
                'felony_conviction', 'felony_description',
            ),
        }),
        
        ('Institution Information', {
            'fields': (
                ('institution_type', 'institution_name'),
                'institution_address',
                ('position_title', 'teaching_subjects'),
                ('teaching_qualification', 'teaching_experience_years'),
                ('institution_accredited', 'accreditation_body', 'accreditation_level'),
                'delivery_methods',
                ('current_student_count', 'max_student_capacity'),
                'curriculum_type',
            ),
        }),
        
        ('Legal Agreements', {
            'fields': (
                'popi_act_accepted', 'terms_accepted', 'information_accurate',
            ),
        }),
    )
    
    readonly_fields = [
        'created_at', 'updated_at', 'created_user',
        'approved', 'approved_at', 'approved_by'
    ]
    
    def get_full_name(self, obj):
        return obj.get_display_name()
    get_full_name.short_description = 'Name'
    
    def document_count(self, obj):
        return obj.documents.count()
    document_count.short_description = 'Documents'


# === DOCUMENT ADMIN ===
@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """
    Professional admin interface for Documents
    """
    list_display = [
        'original_filename', 'category', 'get_related_object', 
        'file_size_display', 'verified', 'uploaded_at'
    ]
    
    list_filter = [
        'category', 'verified', 'uploaded_at', 'content_type'
    ]
    
    search_fields = [
        'original_filename', 'description'
    ]
    
    fieldsets = (
        ('Document Information', {
            'fields': (
                'category', 'file', 'description',
            ),
        }),
        
        ('Verification', {
            'fields': (
                'verified', 'verified_by', 'verified_at',
            ),
        }),
        
        ('Related Object', {
            'fields': (
                ('content_type', 'object_id'),
            ),
            'classes': ('collapse',),
        }),
    )
    
    readonly_fields = [
        'uploaded_at', 'uploaded_by', 'original_filename', 
        'file_size', 'mime_type', 'verified_at'
    ]
    
    def get_related_object(self, obj):
        if obj.content_object:
            return str(obj.content_object)
        return 'No related object'
    get_related_object.short_description = 'Related To'
    
    def file_size_display(self, obj):
        return obj.get_file_size_display()
    file_size_display.short_description = 'File Size'


# === REGISTRATION SESSION ADMIN ===
@admin.register(RegistrationSession)
class RegistrationSessionAdmin(admin.ModelAdmin):
    """
    Admin interface for Registration Sessions
    """
    list_display = [
        'session_key', 'registration_type', 'user', 
        'status', 'completed', 'created_at'
    ]
    
    list_filter = [
        'registration_type', 'status', 'completed', 'created_at'
    ]
    
    search_fields = [
        'session_key', 'user__username', 'user__email', 'ip_address'
    ]
    
    fieldsets = (
        ('Session Information', {
            'fields': (
                'session_key', 'registration_type', 'user',
                ('status', 'completed'),
            ),
        }),
        
        ('Technical Details', {
            'fields': (
                'ip_address', 'user_agent',
            ),
            'classes': ('collapse',),
        }),
        
        ('Notes', {
            'fields': (
                'notes',
            ),
        }),
    )
    
    readonly_fields = ['created_at']


# === ADMIN SITE CUSTOMIZATION ===
admin.site.site_header = 'Ministry Professional Council Administration'
admin.site.site_title = 'MPC Admin'
admin.site.index_title = 'Welcome to Ministry Professional Council Administration'