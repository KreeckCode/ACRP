from django.contrib import admin
from .models import CGMPAffiliation, CPSCAffiliation, CMTPAffiliation, Document, RegistrationSession


# No custom list_display → no E108 errors
admin.site.register(CGMPAffiliation)
admin.site.register(CPSCAffiliation)
admin.site.register(CMTPAffiliation)
admin.site.register(Document)
admin.site.register(RegistrationSession)
