from django.contrib import admin
from .models import (
    LearnerProfile, AcademicHistory,
    LearnerQualificationEnrollment,
    CPDEvent, CPDHistory,
    LearnerAffiliation, DocumentType,
    LearnerDocument
)

class AcademicHistoryInline(admin.TabularInline):
    model = AcademicHistory
    extra = 0

class EnrollmentInline(admin.TabularInline):
    model = LearnerQualificationEnrollment
    extra = 0

class CPDHistoryInline(admin.TabularInline):
    model = CPDHistory
    extra = 0

class AffiliationInline(admin.TabularInline):
    model = LearnerAffiliation
    extra = 0

class LearnerDocumentInline(admin.TabularInline):
    model = LearnerDocument
    extra = 0

@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
    list_display  = ('user','id_number','status')
    list_filter   = ('status','nationality')
    search_fields = ('user__username','id_number')
    inlines       = [AcademicHistoryInline, EnrollmentInline, CPDHistoryInline, AffiliationInline, LearnerDocumentInline]

@admin.register(AcademicHistory)
class AcademicHistoryAdmin(admin.ModelAdmin):
    list_display  = ('learner','institution_name','qualification_name','completion_date')
    list_filter   = ('completion_date',)
    search_fields = ('learner__id_number','institution_name','qualification_name')

@admin.register(LearnerQualificationEnrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display  = ('learner','qualification','status','enrolled_date','completion_date')
    list_filter   = ('status','qualification')
    search_fields = ('learner__id_number','qualification__name')

@admin.register(CPDEvent)
class CPDEventAdmin(admin.ModelAdmin):
    list_display  = ('date','delivery_type','topics')
    list_filter   = ('delivery_type','date')
    search_fields = ('topics',)

@admin.register(CPDHistory)
class CPDHistoryAdmin(admin.ModelAdmin):
    list_display  = ('learner','event','date_attended','points_awarded','verification_status')
    list_filter   = ('verification_status','date_attended')
    search_fields = ('learner__id_number','event__topics')

@admin.register(LearnerAffiliation)
class AffiliationAdmin(admin.ModelAdmin):
    list_display  = ('learner','organization_name','affiliation_date','status')
    list_filter   = ('status','organization_name')
    search_fields = ('learner__id_number','organization_name')

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display  = ('code','description')
    search_fields = ('code','description')

@admin.register(LearnerDocument)
class LearnerDocumentAdmin(admin.ModelAdmin):
    list_display  = ('learner','document_type','status','uploaded_at')
    list_filter   = ('status','uploaded_at')
    search_fields = ('learner__id_number','document_type__code')
