from django.contrib import admin
from .models import (
    Provider, ProviderAccreditation,
    Qualification, QualificationModule,
    ProviderUserProfile, AssessorProfile,
    ProviderDocument,
)

admin.site.register(Provider)
admin.site.register(ProviderAccreditation)
admin.site.register(Qualification)
admin.site.register(QualificationModule)
admin.site.register(ProviderUserProfile)
admin.site.register(ProviderDocument)
admin.site.register(AssessorProfile)