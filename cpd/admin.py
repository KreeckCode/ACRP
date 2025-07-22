

from django.contrib import admin
from .models import (
    CPDProvider, CPDCategory, CPDRequirement, CPDActivity, 
    CPDPeriod, CPDRecord, CPDEvidence, CPDApproval, 
    CPDCompliance, CPDCertificate, CPDAuditLog
)


@admin.register(CPDProvider)
class CPDProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider_type', 'is_accredited', 'is_active', 'created_at']
    list_filter = ['provider_type', 'is_accredited', 'is_active']
    search_fields = ['name', 'description']
    ordering = ['name']


@admin.register(CPDCategory)
class CPDCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_code', 'points_per_hour', 'requires_approval', 'is_active', 'display_order']
    list_filter = ['requires_approval', 'requires_evidence', 'is_active']
    search_fields = ['name', 'short_code']
    ordering = ['display_order', 'name']


@admin.register(CPDRequirement)
class CPDRequirementAdmin(admin.ModelAdmin):
    list_display = ['name', 'council', 'user_level', 'total_points_required', 'total_hours_required', 'effective_date', 'is_active']
    list_filter = ['council', 'user_level', 'is_active', 'effective_date']
    search_fields = ['name', 'description']
    ordering = ['-effective_date']


@admin.register(CPDActivity)
class CPDActivityAdmin(admin.ModelAdmin):
    list_display = ['title', 'provider', 'category', 'activity_type', 'duration_hours', 'approval_status', 'start_date', 'is_active']
    list_filter = ['approval_status', 'activity_type', 'category', 'provider', 'is_active', 'is_online']
    search_fields = ['title', 'description', 'provider__name']
    ordering = ['-start_date']
    date_hierarchy = 'start_date'


@admin.register(CPDPeriod)
class CPDPeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'submission_deadline', 'is_current']
    list_filter = ['is_current']
    search_fields = ['name']
    ordering = ['-start_date']


@admin.register(CPDRecord)
class CPDRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity', 'period', 'status', 'points_awarded', 'completion_date', 'created_at']
    list_filter = ['status', 'period', 'activity__category', 'completion_date']
    search_fields = ['user__username', 'user__email', 'activity__title', 'custom_title']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'


@admin.register(CPDEvidence)
class CPDEvidenceAdmin(admin.ModelAdmin):
    list_display = ['record', 'evidence_type', 'original_filename', 'is_verified', 'uploaded_at']
    list_filter = ['evidence_type', 'is_verified', 'uploaded_at']
    search_fields = ['record__user__username', 'original_filename', 'description']
    ordering = ['-uploaded_at']


@admin.register(CPDApproval)
class CPDApprovalAdmin(admin.ModelAdmin):
    list_display = ['record', 'status', 'original_points', 'adjusted_points', 'reviewer', 'submitted_at', 'reviewed_at']
    list_filter = ['status', 'priority', 'auto_approved', 'submitted_at']
    search_fields = ['record__user__username', 'record__activity__title', 'reviewer__username']
    ordering = ['-submitted_at']
    date_hierarchy = 'submitted_at'


@admin.register(CPDCompliance)
class CPDComplianceAdmin(admin.ModelAdmin):
    list_display = ['user', 'period', 'compliance_status', 'total_points_earned', 'points_progress_percentage', 'calculated_at']
    list_filter = ['compliance_status', 'period', 'calculated_at']
    search_fields = ['user__username', 'user__email']
    ordering = ['-calculated_at']


@admin.register(CPDCertificate)
class CPDCertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_number', 'user', 'period', 'points_certified', 'issue_date', 'expiry_date', 'is_valid']
    list_filter = ['is_valid', 'issue_date', 'period']
    search_fields = ['certificate_number', 'user__username', 'user__email']
    ordering = ['-issue_date']
    readonly_fields = ['verification_token']


@admin.register(CPDAuditLog)
class CPDAuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'content_type', 'object_id', 'timestamp']
    list_filter = ['action', 'content_type', 'timestamp']
    search_fields = ['user__username', 'notes']
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    readonly_fields = ['user', 'action', 'content_type', 'object_id', 'timestamp', 'field_changes']