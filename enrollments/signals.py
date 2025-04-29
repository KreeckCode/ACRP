import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail

from .models import AssociatedAffiliation
from student.models import LearnerProfile
from providers.models import Provider
from accounts.models import User, Role

logger = logging.getLogger(__name__)

def _create_user_and_profile(instance: AssociatedAffiliation):
    """
    1) Create (or replace) instance.created_user with a LEARNER User:
         • username = email
         • password = id_number
         • first_name, last_name, phone, is_active=True
    2) Save that user to instance.created_user.
    3) Create LearnerProfile for that user (assigning a provider).
    Returns (user, raw_password or None)
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
    username     = instance.email.lower()
    learner_role, _ = Role.objects.get_or_create(title='Learner')

    logger.info("📥 Creating learner User for Affiliation %s: %s", instance.pk, username)
    new_user = User.objects.create_user(
        username    = username,
        email       = instance.email,
        password    = raw_password,
        first_name  = instance.first_name or "",
        last_name   = instance.last_name or "",
        acrp_role   = User.ACRPRole.LEARNER,
        role        = learner_role,
        phone       = instance.cell or "",
        is_active   = True,  
    )

    logger.info(
        "✅ Created User: username='%s', email='%s', first_name='%s', last_name='%s', phone='%s', is_active=%s",
        new_user.username, new_user.email, new_user.first_name, new_user.last_name, new_user.phone, new_user.is_active
    )

    # Link user back to the affiliation
    instance.created_user = new_user
    instance.save(update_fields=['created_user'])
    logger.info("🔗 Linked User %s to AssociatedAffiliation %s", new_user.username, instance.pk)

    # Ensure a provider exists
    provider = Provider.objects.first()
    if not provider:
        logger.warning("⚠️ No Provider found; LearnerProfile will have provider=None")

    # Create or get the LearnerProfile
    profile, created = LearnerProfile.objects.get_or_create(
        user=new_user,
        defaults={
            'provider'          : provider,
            'id_number'         : instance.id_number,
            'date_of_birth'     : instance.date_of_birth,
            'gender'            : instance.gender,
            'phone'             : instance.cell,
            'email'             : instance.email,
            'address'           : instance.postal_address,
            'nationality'       : '',
            'primary_language'  : instance.home_language or '',
            'emergency_name'    : '',
            'emergency_relation': '',
            'emergency_phone'   : ''
        }
    )
    if created:
        logger.info("✅ Created LearnerProfile %s for user %s", profile.pk, new_user.username)
    else:
        logger.debug("LearnerProfile already existed for user %s", new_user.username)

    return new_user, raw_password




def _make_learner_profile(instance):
    """
    Create a LearnerProfile for the newly created_user on an approved affiliation,
    ensuring the required 'provider' FK is set.
    """
    user = instance.created_user
    if not user:
        logger.debug("No created_user on instance %s, skipping profile creation.", instance.pk)
        return

    if hasattr(user, 'learner_profile'):
        logger.debug("LearnerProfile already exists for user %s, skipping.", user.username)
        return

    # Determine which Provider to assign
    provider = getattr(instance, 'provider', None) or Provider.objects.first()
    if not provider:
        logger.warning("No Provider found; creating LearnerProfile without provider.")

    profile = LearnerProfile.objects.create(
        user=user,
        provider=provider,
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
    logger.info("Created LearnerProfile %s for user %s", profile.pk, user.username)



@receiver(post_save, sender=AssociatedAffiliation)
def on_approve_create_user(sender, instance, created, **kwargs):
    """
    When an existing AssociatedAffiliation is marked approved:
      - Create learner User + profile if needed (with all fields)
      - Send credentials via email (or print/log in DEBUG)
    """
    if created:
        logger.debug("ℹ️ Affiliation %s created; awaiting approval.", instance.pk)
        return

    if not instance.approved:
        logger.debug("ℹ️ Affiliation %s saved without approval.", instance.pk)
        return

    logger.info("✅ Affiliation %s approved; creating user/profile.", instance.pk)
    user, raw_pw = _create_user_and_profile(instance)

    if raw_pw:
        subject = "Your ACRP application has been approved"
        message = (
            f"Hello {instance.first_name} {instance.last_name},\n\n"
            "Your associated application is approved!\n\n"
            f"Username: {user.username}\n"
            f"Password: {raw_pw}\n\n"
            "Please log in and change your password ASAP.\n\n"
            "Kind regards,\nACRP Team"
        )
        if settings.DEBUG:
            logger.debug("🔧 DEBUG mode: credentials email suppressed:\n%s", message)
            print("=== APPROVAL EMAIL (DEBUG) ===")
            print(message)
            print("=== END ===")
        else:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            logger.info("✉️ Sent approval email to %s", user.email)
    else:
        logger.debug("ℹ️ No new credentials to email for affiliation %s", instance.pk)

        
# ————————————————
# CLEANUP SIGNALS
# ————————————————

@receiver(post_delete, sender=LearnerProfile)
def delete_associated_on_profile_delete(sender, instance, **kwargs):
    """
    When a LearnerProfile is deleted, also delete any AssociatedAffiliation
    that was linked via created_user.
    """
    user = instance.user
    qs = AssociatedAffiliation.objects.filter(created_user=user)
    count = qs.count()
    if count:
        qs.delete()
        logger.info("Deleted %d AssociatedAffiliation(s) for removed learner %s", count, user.username)


@receiver(post_delete, sender=User)
def delete_associated_on_user_delete(sender, instance, **kwargs):
    """
    When a User is deleted, also delete any AssociatedAffiliation
    that was linked via created_user.
    """
    qs = AssociatedAffiliation.objects.filter(created_user=instance)
    count = qs.count()
    if count:
        qs.delete()
        logger.info("Deleted %d AssociatedAffiliation(s) for removed user %s", count, instance.username)