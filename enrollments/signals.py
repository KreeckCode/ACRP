import logging
from typing import Tuple, Optional, Type

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.core.mail import send_mail
from django.db import models

from .models import CGMPAffiliation, CPSCAffiliation, CMTPAffiliation
from student.models import LearnerProfile 
from providers.models import Provider
from accounts.models import User, Role

logger = logging.getLogger(__name__)

# Type alias for affiliation models
AffiliationType = Type[models.Model]
AFFILIATION_MODELS = (CGMPAffiliation, CPSCAffiliation, CMTPAffiliation)

def _create_user_and_profile(instance: models.Model) -> Tuple[User, Optional[str]]:
    """
    Creates a user account and learner profile for approved affiliations.
    
    Args:
        instance: Any affiliation model instance inheriting from BaseAffiliation
        
    Returns:
        Tuple of (User, raw_password or None)
    """
    need_new = (
        instance.created_user is None or
        instance.created_user.acrp_role != User.ACRPRole.LEARNER
    )

    if not need_new:
        logger.debug(
            "Affiliation %s already has learner user %s; skipping creation.",
            instance.pk, instance.created_user.username
        )
        return instance.created_user, None

    raw_password = instance.id_number
    username = instance.email.lower()
    learner_role, _ = Role.objects.get_or_create(title='Learner')

    try:
        logger.info("Creating learner User for %s Affiliation %s: %s", 
                   instance.__class__.__name__, instance.pk, username)
        
        new_user = User.objects.create_user(
            username=username,
            email=instance.email,
            password=raw_password,
            first_name=instance.first_name,
            last_name=instance.last_name,
            acrp_role=User.ACRPRole.LEARNER,
            role=learner_role,
            phone=instance.cell,
            is_active=True,
        )

        # Link user back to affiliation
        instance.created_user = new_user
        instance.save(update_fields=['created_user'])

        # Create learner profile
        provider = Provider.objects.first()
        if not provider:
            logger.warning("No Provider found; LearnerProfile will have provider=None")

        profile, created = LearnerProfile.objects.get_or_create(
            user=new_user,
            defaults={
                'provider': provider,
                'id_number': instance.id_number,
                'date_of_birth': instance.date_of_birth,
                'gender': instance.gender,
                'phone': instance.cell,
                'email': instance.email,
                'address': instance.postal_address,
                'nationality': instance.country,
                'primary_language': instance.home_language,
                'emergency_name': '',
                'emergency_relation': '',
                'emergency_phone': ''
            }
        )

        if created:
            logger.info("Created LearnerProfile %s for user %s", profile.pk, new_user.username)
        
        return new_user, raw_password

    except Exception as e:
        logger.error("Failed to create user for affiliation %s: %s", instance.pk, str(e))
        raise

def _send_approval_email(user: User, raw_pw: str, instance: models.Model) -> None:
    """Sends approval email with login credentials"""
    
    subject = "Your ACRP Application has been Approved"
    message = (
        f"Hello {instance.first_name} {instance.last_name},\n\n"
        f"Your {instance.__class__.__name__} application has been approved!\n\n"
        f"Username: {user.username}\n"
        f"Password: {raw_pw}\n\n"
        "Please log in and change your password immediately.\n\n"
        "Kind regards,\nACRP Team"
    )

    if settings.DEBUG:
        logger.debug("DEBUG mode: Suppressed email:\n%s", message)
        return

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Sent approval email to %s", user.email)
    except Exception as e:
        logger.error("Failed to send approval email to %s: %s", user.email, str(e))

# Register signals for all affiliation types
for model in AFFILIATION_MODELS:
    @receiver(post_save, sender=model)
    def on_approve_create_user(sender, instance, created, **kwargs):
        """Handle user creation on affiliation approval"""
        if created or not instance.approved:
            return

        try:
            user, raw_pw = _create_user_and_profile(instance)
            if raw_pw:
                _send_approval_email(user, raw_pw, instance)
        except Exception as e:
            logger.error("Error in approval process for %s %s: %s", 
                        sender.__name__, instance.pk, str(e))

    @receiver(post_delete, sender=model)
    def cleanup_on_delete(sender, instance, **kwargs):
        """Clean up associated user and profile on affiliation deletion"""
        if instance.created_user:
            try:
                instance.created_user.delete()
                logger.info("Deleted user %s after %s deletion", 
                          instance.created_user.username, sender.__name__)
            except Exception as e:
                logger.error("Failed to delete user for %s %s: %s",
                           sender.__name__, instance.pk, str(e))
