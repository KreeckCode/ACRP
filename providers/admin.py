# provider/admin.py
from django.contrib import admin
from .models import (
    Provider, ProviderAccreditation,
    Qualification, QualificationModule,
    ProviderUserProfile, AssessorProfile,
    ProviderDocument
)

class AccreditationInline(admin.TabularInline):
    model = ProviderAccreditation
    extra = 1

class ModuleInline(admin.TabularInline):
    model = QualificationModule
    extra = 1

class QualificationInline(admin.StackedInline):
    model   = Qualification
    extra   = 1
    inlines = [ModuleInline]

class DocumentInline(admin.TabularInline):
    model = ProviderDocument
    extra = 1

@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display  = ('code','trade_name','status','created_at','updated_at')
    list_filter   = ('status','created_at')
    search_fields = ('code','trade_name','legal_name')
    inlines       = [AccreditationInline, QualificationInline, DocumentInline]

@admin.register(ProviderAccreditation)
class AccreditationAdmin(admin.ModelAdmin):
    list_display  = ('provider','code','name','status','start_date','expiry_date')
    list_filter   = ('status','accrediting_body')
    search_fields = ('provider__code','code','name')

@admin.register(Qualification)
class QualificationAdmin(admin.ModelAdmin):
    list_display  = ('name','provider','level','credit_value')
    list_filter   = ('level','provider')
    search_fields = ('name','provider__code')
    inlines       = [ModuleInline]

@admin.register(QualificationModule)
class ModuleAdmin(admin.ModelAdmin):
    list_display  = ('qualification','code','name','order')
    list_filter   = ('qualification',)
    search_fields = ('code','name')

@admin.register(ProviderUserProfile)
class ProviderUserAdmin(admin.ModelAdmin):
    list_display  = ('user','provider','role')
    list_filter   = ('role','provider')
    search_fields = ('user__username','provider__code')

@admin.register(AssessorProfile)
class AssessorAdmin(admin.ModelAdmin):
    list_display  = ('first_name','last_name','provider','status')
    list_filter   = ('status','provider')
    search_fields = ('first_name','last_name','id_number')

@admin.register(ProviderDocument)
class DocumentAdmin(admin.ModelAdmin):
    list_display  = ('provider','name','status','uploaded_at')
    list_filter   = ('status','uploaded_at')
    search_fields = ('provider__code','name')
