from django.contrib import admin
from .models import AssociatedAffiliation, DesignatedAffiliation, StudentAffiliation

# No custom list_display → no E108 errors
admin.site.register(AssociatedAffiliation)
admin.site.register(DesignatedAffiliation)
admin.site.register(StudentAffiliation)
