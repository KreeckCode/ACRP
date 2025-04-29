from django.apps import AppConfig


class StudentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student"

    def ready(self):
        # import our signals so Django will register them
        import student.signals
