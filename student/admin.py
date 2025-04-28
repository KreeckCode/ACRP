from django.contrib import admin
from .models import (
    LearnerProfile, AcademicHistory,
    LearnerQualificationEnrollment,
    CPDEvent, CPDHistory,
    LearnerAffiliation, DocumentType,
    LearnerDocument
)
admin.site.register(LearnerProfile)
admin.site.register(AcademicHistory)
admin.site.register(LearnerQualificationEnrollment)
admin.site.register(CPDEvent)
admin.site.register(CPDHistory)
admin.site.register(LearnerAffiliation)
admin.site.register(DocumentType)
admin.site.register(LearnerDocument)