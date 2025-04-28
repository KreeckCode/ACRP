from django.contrib import admin
from .models import AssociatedAffiliation

# No custom list_display → no E108 errors
admin.site.register(AssociatedAffiliation)
