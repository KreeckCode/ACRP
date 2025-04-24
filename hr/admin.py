from django.contrib import admin
from django.utils import timezone
from .models import *

# Register the models
admin.site.register(EmployeeProfile)
admin.site.register(EmployeeDocument)
admin.site.register(LeaveRequest)
admin.site.register(LeaveType)
admin.site.register(EmployeeWarning)
admin.site.register(HRDocumentStorage)
admin.site.register(DocumentAccessLog)
admin.site.register(Payslip)
admin.site.register(DocumentRequest)
admin.site.register(DocumentShare)