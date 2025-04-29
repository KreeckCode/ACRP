from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging
from .models import LearnerProfile, LearnerAffiliation, LearnerDocument

User = get_user_model()
logger = logging.getLogger(__name__)

def try_activate_learner(profile: LearnerProfile):
    """
    Activate the linked User when:
      • profile.verification_status == VERIFIED
      • at least one affiliation is VERIFIED
      • at least one document is VERIFIED
    """
    logger.debug("Checking activation for LearnerProfile %s", profile.pk)

    if profile.verification_status != 'VERIFIED':
        logger.debug("Profile %s not VERIFIED, skipping activation.", profile.pk)
        return

    has_aff = profile.affiliations.filter(verification_status='VERIFIED').exists()
    has_doc = profile.documents.filter(verification_status='VERIFIED').exists()
    logger.debug("Profile %s has_aff=%s has_doc=%s", profile.pk, has_aff, has_doc)

    if has_aff and has_doc and not profile.user.is_active:
        profile.user.is_active = True
        profile.user.save(update_fields=['is_active'])
        logger.info("Activated user %s for LearnerProfile %s", profile.user.username, profile.pk)

        if not settings.DEBUG:
            send_mail(
                subject="[ACRP] Your account is now active",
                message=(
                    f"Hello {profile.user.get_full_name()},\n\n"
                    "Your learner account is now active. You can log in and access your dashboard.\n\n"
                    "Welcome aboard!\nACRP Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[profile.email],
                fail_silently=True,
            )
            logger.info("Sent activation email to %s", profile.email)
        else:
            logger.debug("DEBUG mode: activation email suppressed for %s", profile.email)


@receiver(post_save, sender=User)
def on_user_created(sender, instance, created, **kwargs):
    """
    1) When a new LEARNER User is created, deactivate it.
    2) Ensure there's a stub LearnerProfile.
    """
    if not created:
        return

    if instance.acrp_role == User.ACRPRole.LEARNER:
        '''
        if instance.is_active:
            instance.is_active = False
            instance.save(update_fields=['is_active'])
            logger.debug("Deactivated new learner user %s", instance.username)
        '''
        profile, created_profile = LearnerProfile.objects.get_or_create(
            user=instance,
            defaults={
                'id_number':        instance.username,
                'date_of_birth':    '1900-01-01',
                'gender':           'O',
                'phone':            '',
                'email':            instance.email or '',
                'address':          '',
                'nationality':      '',
                'primary_language': '',
                'emergency_name':   '',
                'emergency_relation': '',
                'emergency_phone':  '',
            }
        )
        if created_profile:
            logger.info("Created stub LearnerProfile %s for new user %s", profile.pk, instance.username)
        else:
            logger.debug("LearnerProfile already existed for new user %s", instance.username)




@receiver(post_save, sender=LearnerProfile)
def on_profile_saved(sender, instance, created, **kwargs):
    if created:
        logger.debug("New LearnerProfile %s created", instance.pk)
    else:
        logger.debug("LearnerProfile %s updated (status=%s)",
                     instance.pk, instance.verification_status)
    if not created and instance.verification_status == 'VERIFIED':
        try_activate_learner(instance)


@receiver(post_save, sender=LearnerAffiliation)
def on_affiliation_saved(sender, instance, **kwargs):
    logger.debug("LearnerAffiliation %s saved (status=%s)",
                 instance.pk, instance.verification_status)
    if instance.verification_status == 'VERIFIED':
        try_activate_learner(instance.learner)


@receiver(post_save, sender=LearnerDocument)
def on_document_saved(sender, instance, **kwargs):
    logger.debug("LearnerDocument %s saved (status=%s)",
                 instance.pk, instance.verification_status)
    if instance.verification_status == 'VERIFIED':
        try_activate_learner(instance.learner)

from .models import LearnerProfile, LearnerAffiliation, LearnerDocument, LearnerQualificationEnrollment
from django.db.models.signals import post_save, post_delete
@receiver(post_delete, sender=LearnerQualificationEnrollment)
def cleanup_on_enrollment_delete(sender, instance, **kwargs):
    """
    When a LearnerQualificationEnrollment is deleted,
    if that learner has no more enrollments, remove their LearnerProfile and then their User.
    """
    profile = instance.learner
    # Only proceed if no remaining enrollments
    if not profile.enrollments.exists():
        user = profile.user
        logger.info("No more enrollments for learner %s; deleting profile %s", user.username, profile.pk)
        profile.delete()
        logger.info("Deleted LearnerProfile %s", profile.pk)
        user.delete()
        logger.info("Deleted User %s", user.username)