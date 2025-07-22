from django.contrib import admin
from .models import *

admin.site.register(AffiliationCard)
admin.site.register(CardTemplate)
admin.site.register(CardDelivery)
admin.site.register(CardStatusChange)
admin.site.register(CardSystemSettings)
admin.site.register(CardVerification)