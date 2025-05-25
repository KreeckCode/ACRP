from django.contrib import admin
from .models import Event, Announcement, Projects, Task, Resource, Quiz, Question, Answer


admin.site.register(Event)
admin.site.register(Announcement)
#admin.site.register(Notification)
admin.site.register(Projects)
admin.site.register(Task)
admin.site.register(Resource)
admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Answer)