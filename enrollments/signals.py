from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail

from .models import AssociatedAffiliation
from student.models import LearnerProfile
from accounts.models import User, Role

def _make_learner(instance):
    """
    Provision a LearnerProfile once the affiliation is approved.
    """
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
            emergency_name='',
            emergency_relation='',
            emergency_phone=''
        )

@receiver(post_save, sender=AssociatedAffiliation)
def on_approve_create_user(sender, instance, created, **kwargs):
    """
    When an existing AssociatedAffiliation is marked approved:
     - Stamp approved_at (once)
     - Create a User if none exists
     - Provision a LearnerProfile
     - Send an approval email (only if not in DEBUG)
    """
    # Only proceed on updates (not on initial create) and only if approved=True
    if created or not instance.approved:
        return

    fields_to_save = []

    # 1) Stamp approval time exactly once
    if instance.approved_at is None:
        instance.approved_at = timezone.now()
        fields_to_save.append('approved_at')

    # 2) Create a new User if none exists yet
    if instance.created_user is None:
        learner_role, _ = Role.objects.get_or_create(title='Learner')
        new_user = User.objects.create_user(
            username=f"{instance.surname.lower()}{instance.id_number[-4:]}",
            email=instance.email,
            password=User.objects.make_random_password(),
            acrp_role=User.ACRPRole.LEARNER,
            role=learner_role
        )
        instance.created_user = new_user
        fields_to_save.append('created_user')

    # Only save if we changed something
    if fields_to_save:
        instance.save(update_fields=fields_to_save)

    # 3) Provision the LearnerProfile
    _make_learner(instance)

    # 4) Send approval email once (only in production)
    #    We send only if we just stamped approved_at above.
    if instance.approved_at and not settings.DEBUG:
        subject = "Your ACRP associated application has been approved"
        message = (
            f"Dear {instance.first_name} {instance.last_name},\n\n"
            "Congratulations! Your associated application has been approved.\n\n"
            "You may now log in to your account and access all available features.\n\n"
            "Kind regards,\n"
            "The ACRP Team"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
            fail_silently=False,
        )
