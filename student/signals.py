# student/signals.py

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import LearnerProfile, LearnerAffiliation, LearnerDocument

User = get_user_model()


def try_activate_learner(profile: LearnerProfile):
    """
    Activate the linked User only when:
      • profile.verification_status == VERIFIED
      • at least one affiliation is VERIFIED
      • at least one document is VERIFIED
    """
    if profile.verification_status != 'VERIFIED':
        return

    has_aff = profile.affiliations.filter(verification_status='VERIFIED').exists()
    has_doc = profile.documents.filter(verification_status='VERIFIED').exists()

    if has_aff and has_doc and not profile.user.is_active:
        profile.user.is_active = True
        profile.user.save(update_fields=['is_active'])

        # Only send real emails in production
        if not settings.DEBUG:
            send_mail(
                subject="[ACRP] Your account is now active",
                message=(
                    f"Hello {profile.user.get_full_name()},\n\n"
                    "Your ACRP learner account has been approved and is now active. "
                    "You can now log in and access your dashboard.\n\n"
                    "Welcome aboard!\n\nACRP Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[profile.email],
                fail_silently=True,
            )


@receiver(post_save, sender=User)
def on_user_created(sender, instance, created, **kwargs):
    """
    1) When a new LEARNER User is created → set is_active=False
    2) Ensure there's always a LearnerProfile stub.
    """
    if not created:
        return

    if instance.acrp_role == User.ACRPRole.LEARNER:
        # 1) Deactivate until all verifications pass
        if instance.is_active:
            instance.is_active = False
            instance.save(update_fields=['is_active'])

        # 2) Create a minimal LearnerProfile if none exists
        LearnerProfile.objects.get_or_create(
            user=instance,
            defaults={
                'id_number':       instance.username,
                'date_of_birth':   '1900-01-01',
                'gender':          'O',
                'phone':           '',
                'email':           instance.email or '',
                'address':         '',
                'nationality':     '',
                'primary_language':'',
                'emergency_name':  '',
                'emergency_relation':'',
                'emergency_phone': '',
            }
        )


@receiver(post_save, sender=LearnerProfile)
def on_profile_saved(sender, instance, created, **kwargs):
    if not created and instance.verification_status == 'VERIFIED':
        try_activate_learner(instance)


@receiver(post_save, sender=LearnerAffiliation)
def on_affiliation_saved(sender, instance, **kwargs):
    if instance.verification_status == 'VERIFIED':
        try_activate_learner(instance.learner)


@receiver(post_save, sender=LearnerDocument)
def on_document_saved(sender, instance, **kwargs):
    if instance.verification_status == 'VERIFIED':
        try_activate_learner(instance.learner)
