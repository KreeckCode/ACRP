
class EnrollmentsRouter:
    enrollments_db = 'enrollments'
    default_db = 'default'

    def db_for_read(self, model, **hints):
        model_name = model._meta.model_name
        if model_name == 'enrollments':
            return self.enrollments_db
        else:
            return None
        
    def db_for_write(self, model, **hints):
        model_name = model._meta.model_name

        if model_name == 'enrollments':
            return 'enrollments'
        else:
            return None
        

    def allow_migrate(self, db, app_level, model_name=None, **hints):
        if model_name == 'enrollments':
            return db == 'enrollments'
        else:
            return db == 'default'
        