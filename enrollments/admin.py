# enrollments/admin.py - Simple admin configuration

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    # Core models
    Council,
    AffiliationType,
    DesignationCategory,
    DesignationSubcategory,
    OnboardingSession,
    
    # Application models
    AssociatedApplication,
    DesignatedApplication,
    StudentApplication,
    
    # Related models
    AcademicQualification,
    Reference,
    PracticalExperience,
    Document,
)


# ============================================================================
# CORE REFERENCE DATA ADMIN
# ============================================================================

@admin.register(Council)
class CouncilAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'has_subcategories', 'is_active']
    list_filter = ['has_subcategories', 'is_active']
    search_fields = ['code', 'name']
    list_editable = ['is_active']


@admin.register(AffiliationType)
class AffiliationTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'requires_designation_category', 'is_active']
    list_filter = ['requires_designation_category', 'is_active']
    search_fields = ['code', 'name']
    list_editable = ['is_active']


@admin.register(DesignationCategory)
class DesignationCategoryAdmin(admin.ModelAdmin):
    list_display = ['level', 'code', 'name', 'is_active']
    list_filter = ['level', 'is_active']
    search_fields = ['code', 'name']
    list_editable = ['is_active']
    ordering = ['level']


@admin.register(DesignationSubcategory)
class DesignationSubcategoryAdmin(admin.ModelAdmin):
    list_display = ['category', 'council', 'name', 'is_active']
    list_filter = ['category', 'council', 'is_active']
    search_fields = ['code', 'name']
    list_editable = ['is_active']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category', 'council')


# ============================================================================
# ONBOARDING SESSION ADMIN
# ============================================================================

@admin.register(OnboardingSession)
class OnboardingSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'user', 'get_affiliation_type', 'get_council', 'status', 'created_at', 'completed_at']
    list_filter = ['status', 'selected_affiliation_type', 'selected_council', 'created_at']
    search_fields = ['session_id', 'user__username', 'user__email']
    readonly_fields = ['session_id', 'created_at', 'updated_at']
    
    def get_affiliation_type(self, obj):
        return obj.selected_affiliation_type.name if obj.selected_affiliation_type else '-'
    get_affiliation_type.short_description = 'Affiliation Type'
    
    def get_council(self, obj):
        return obj.selected_council.code if obj.selected_council else '-'
    get_council.short_description = 'Council'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'selected_affiliation_type', 'selected_council'
        )


# ============================================================================
# APPLICATION ADMIN CLASSES
# ============================================================================

class BaseApplicationAdmin(admin.ModelAdmin):
    """Base admin class for all application types"""
    
    list_display = [
        'application_number', 'get_full_name', 'email', 'get_council', 
        'get_affiliation_type', 'status', 'created_at'
    ]
    list_filter = ['status', 'created_at', 'onboarding_session__selected_council']
    search_fields = ['application_number', 'full_names', 'surname', 'email']
    readonly_fields = ['application_number', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Application Info', {
            'fields': ('application_number', 'onboarding_session', 'status')
        }),
        ('Personal Information', {
            'fields': (
                'title', 'gender', 'surname', 'initials', 'full_names', 'preferred_name',
                'id_number', 'passport_number', 'date_of_birth', 'race', 'disability'
            )
        }),
        ('Contact Information', {
            'fields': (
                'email', 'cell_phone', 'work_phone', 'home_phone', 'fax',
                'postal_address_line1', 'postal_address_line2', 'postal_city',
                'postal_province', 'postal_code', 'postal_country'
            )
        }),
        ('Background', {
            'fields': (
                'religious_affiliation', 'home_language', 'other_languages',
                'highest_qualification', 'qualification_institution', 'qualification_date',
                'current_occupation', 'work_description', 'years_in_ministry'
            )
        }),
        ('Legal Agreements', {
            'fields': (
                'popi_act_accepted', 'terms_accepted', 
                'information_accurate', 'declaration_accepted'
            )
        }),
        ('Review', {
            'fields': (
                'reviewed_at', 'reviewed_by', 'reviewer_notes',
                'approved_at', 'approved_by', 'rejected_at', 'rejected_by', 'rejection_reason'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def get_full_name(self, obj):
        return f"{obj.full_names} {obj.surname}"
    get_full_name.short_description = 'Full Name'
    
    def get_council(self, obj):
        return obj.onboarding_session.selected_council.code if obj.onboarding_session.selected_council else '-'
    get_council.short_description = 'Council'
    
    def get_affiliation_type(self, obj):
        return obj.onboarding_session.selected_affiliation_type.code if obj.onboarding_session.selected_affiliation_type else '-'
    get_affiliation_type.short_description = 'Type'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'onboarding_session__selected_council',
            'onboarding_session__selected_affiliation_type'
        )


@admin.register(AssociatedApplication)
class AssociatedApplicationAdmin(BaseApplicationAdmin):
    pass


@admin.register(StudentApplication)
class StudentApplicationAdmin(BaseApplicationAdmin):
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = list(BaseApplicationAdmin.fieldsets)
        # Insert student-specific fields after background
        student_fields = (
            'Student Information', {
                'fields': (
                    'current_institution', 'course_of_study', 'expected_graduation',
                    'student_number', 'year_of_study',
                    'academic_supervisor_name', 'academic_supervisor_email', 'academic_supervisor_phone'
                )
            }
        )
        fieldsets.insert(-2, student_fields)  # Insert before Legal Agreements
        return fieldsets


@admin.register(DesignatedApplication)
class DesignatedApplicationAdmin(BaseApplicationAdmin):
    
    list_display = BaseApplicationAdmin.list_display + ['get_designation_category']
    list_filter = BaseApplicationAdmin.list_filter + ['designation_category']
    
    def get_designation_category(self, obj):
        return obj.designation_category.name if obj.designation_category else '-'
    get_designation_category.short_description = 'Category'
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = list(BaseApplicationAdmin.fieldsets)
        # Insert designation-specific fields after background
        designation_fields = (
            'Designation Information', {
                'fields': (
                    'designation_category', 'designation_subcategory',
                    'high_school_name', 'high_school_year_completed'
                )
            }
        )
        supervision_fields = (
            'Supervision Details', {
                'fields': (
                    'supervisor_name', 'supervisor_qualification', 'supervisor_email',
                    'supervisor_phone', 'supervisor_address', 'supervision_hours_received',
                    'supervision_period_start', 'supervision_period_end'
                )
            }
        )
        professional_fields = (
            'Professional Development', {
                'fields': (
                    'professional_development_plans', 'other_professional_memberships'
                )
            }
        )
        
        # Insert all before Legal Agreements
        fieldsets.insert(-2, designation_fields)
        fieldsets.insert(-2, supervision_fields)
        fieldsets.insert(-2, professional_fields)
        return fieldsets


# ============================================================================
# RELATED MODEL ADMIN
# ============================================================================

@admin.register(AcademicQualification)
class AcademicQualificationAdmin(admin.ModelAdmin):
    list_display = ['application', 'qualification_type', 'qualification_name', 'institution_name', 'date_awarded']
    list_filter = ['qualification_type', 'date_awarded']
    search_fields = ['qualification_name', 'institution_name']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('application')


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ['get_application', 'reference_name', 'reference_email', 'nature_of_relationship', 'letter_required', 'letter_received']
    list_filter = ['letter_required', 'letter_received', 'created_at']
    search_fields = ['reference_surname', 'reference_names', 'reference_email']
    
    def reference_name(self, obj):
        return f"{obj.reference_names} {obj.reference_surname}"
    reference_name.short_description = 'Reference Name'
    
    def get_application(self, obj):
        return str(obj.content_object) if obj.content_object else '-'
    get_application.short_description = 'Application'


@admin.register(PracticalExperience)
class PracticalExperienceAdmin(admin.ModelAdmin):
    list_display = ['application', 'institution_name', 'contact_person_name', 'start_date', 'end_date']
    list_filter = ['start_date', 'end_date']
    search_fields = ['institution_name', 'contact_person_name']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('application')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['get_application', 'category', 'title', 'file_name', 'get_file_size', 'uploaded_at', 'verified']
    list_filter = ['category', 'verified', 'uploaded_at']
    search_fields = ['title', 'original_filename']
    readonly_fields = ['original_filename', 'file_size', 'mime_type', 'uploaded_at']
    
    def file_name(self, obj):
        return obj.original_filename
    file_name.short_description = 'File Name'
    
    def get_file_size(self, obj):
        return obj.get_file_size_display()
    get_file_size.short_description = 'File Size'
    
    def get_application(self, obj):
        return str(obj.content_object) if obj.content_object else '-'
    get_application.short_description = 'Application'


# ============================================================================
# ADMIN SITE CUSTOMIZATION
# ============================================================================

# Customize admin site headers
admin.site.site_header = "ACRP Enrollment Administration"
admin.site.site_title = "ACRP Admin"
admin.site.index_title = "Enrollment Management"