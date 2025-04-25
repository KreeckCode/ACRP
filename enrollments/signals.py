from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import AssociatedAffiliation, DesignatedAffiliation, StudentAffiliation
from student.models import LearnerProfile     # your student app :contentReference[oaicite:13]{index=13}
from accounts.models import User, Role         # your accounts app

# Helper to provision LearnerProfile once approved :contentReference[oaicite:14]{index=14}
def _make_learner(instance):
    user = instance.created_user
    if user and not hasattr(user, 'learner_profile'):
        LearnerProfile.objects.create(
            user=user,
            id_number=instance.id_number,
            date_of_birth=instance.date_of_birth,
            gender=instance.gender,
            phone=instance.cell,
            email=instance.email,
            address=instance.postal_address,
            nationality='',
            primary_language=instance.home_language or '',
            emergency_name='', emergency_relation='', emergency_phone=''
        )

@receiver(post_save, sender=AssociatedAffiliation)
@receiver(post_save, sender=DesignatedAffiliation)
@receiver(post_save, sender=StudentAffiliation)
def on_approve_create_user(sender, instance, created, **kwargs):
    # Only act on existing instance being approved :contentReference[oaicite:15]{index=15}
    if not created and instance.approved:
        # Stamp approval time if not set
        if instance.approved_at is None:
            instance.approved_at = timezone.now()
        # Create a new User if none exists
        if instance.created_user is None:
            learner_role, _ = Role.objects.get_or_create(title='Learner')
            u = User.objects.create_user(
                username=f"{instance.surname.lower()}{instance.id_number[-4:]}",
                email=instance.email,
                password=User.objects.make_random_password(),
                acrp_role=User.ACRPRole.LEARNER,
                role=learner_role
            )
            instance.created_user = u
        instance.save()
        # Then create LearnerProfile in student app
        _make_learner(instance)
