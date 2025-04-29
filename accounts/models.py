from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission, UserManager
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now
from django.conf import settings
from django.urls import reverse
from PIL import Image
from .validators import ASCIIUsernameValidator

class Department(models.Model):
    name        = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    title        = models.CharField(max_length=50, unique=True)
    description  = models.TextField(blank=True, null=True)
    department   = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.CASCADE,
        related_name='roles', help_text="The department this role belongs to."
    )
    parent_role  = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='child_roles'
    )

    def __str__(self):
        return self.title


class User(AbstractUser):
    """
    Extends Django’s AbstractUser with:
     - employee_code, phone, picture
     - org-role → Role + Department + manager hierarchy
     - ACRP-wide role enum & built-in Group/Permission override
    """
    employee_code = models.CharField(max_length=30, unique=True, blank=True, null=True)
    email         = models.EmailField(unique=True)
    phone         = models.CharField(max_length=60, blank=True, null=True)
    picture       = models.ImageField(
        upload_to='profile_pictures/%y/%m/%d/',
        default='default.png', null=True, blank=True
    )
    role          = models.ForeignKey(
        Role, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='users'
    )
    department    = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees'
    )
    date_of_joining = models.DateTimeField(_("date joined"), default=now)
    manager       = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subordinates'
    )

    # override built-in groups/permissions to avoid name clash
    groups           = models.ManyToManyField(
        Group, related_name='custom_user_groups', blank=True
    )
    user_permissions = models.ManyToManyField(
        Permission, related_name='custom_user_permissions', blank=True
    )

    # ACRP-wide roles
    class ACRPRole(models.TextChoices):
        GLOBAL_SDP           = 'GLOBAL_SDP', 'Global (SDP)'
        PROVIDER_ADMIN       = 'PROVIDER_ADMIN', 'Provider Administrator'
        INTERNAL_FACILITATOR = 'INTERNAL_FACILITATOR', 'Internal Facilitator'
        ASSESSOR             = 'ASSESSOR', 'Assessor'
        LEARNER              = 'LEARNER', 'Learner'

    acrp_role = models.CharField(
        max_length=20,
        choices=ACRPRole.choices,
        default=ACRPRole.LEARNER,
        help_text="ACRP-wide role"
    )

    username_validator = ASCIIUsernameValidator()
    objects            = UserManager()

    @property
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

    def get_picture(self):
        try:
            return self.picture.url
        except:
            return settings.MEDIA_URL + 'default.png'

    def get_absolute_url(self):
        return reverse('accounts:user_profile', kwargs={'user_id': self.pk})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # resize uploaded picture
        if self.picture and hasattr(self.picture, 'path'):
            try:
                img = Image.open(self.picture.path)
                if img.height > 300 or img.width > 300:
                    img.thumbnail((300, 300))
                    img.save(self.picture.path)
            except:
                pass

    def delete(self, *args, **kwargs):
        # delete custom picture file
        if self.picture and self.picture.name != 'default.png':
            try:
                self.picture.delete(save=False)
            except:
                pass
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_full_name})"


class StaffUser(models.Model):
    """
    Detailed profile for internal staff.
    """
    user              = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='staff_profile'
    )
    emergency_contact = models.CharField(max_length=60, blank=True, null=True)
    date_of_birth     = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name} [{self.user.department or 'No Dept'}]"
