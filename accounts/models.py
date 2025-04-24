from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission, UserManager
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now
from PIL import Image
from django.conf import settings
from django.urls import reverse
from .validators import ASCIIUsernameValidator


class Department(models.Model):
    """
    Represents a department within the organisation, such as Finance, HR, IT, etc.
    """
    name = models.CharField(max_length=50, unique=True, blank=False, null=False)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    """
    Defines roles such as Software Engineer, Manager, HR, each with specific responsibilities
    within the organisation. Each role must be assigned to a department.
    """
    title = models.CharField(max_length=50, unique=True, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    department = models.ForeignKey(Department,null=True, on_delete=models.CASCADE, related_name='roles', help_text="The department to which this role belongs.")
    parent_role = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_roles')

    def __str__(self):
        return self.title


class User(AbstractUser):
    """
    Custom User model integrated with the Employee Profile.
    When a User is created, an EmployeeProfile is also created automatically.
    """
    employee_code = models.CharField(max_length=30, unique=True, null=False)
    email = models.EmailField(unique=True, blank=False, null=False)
    phone = models.CharField(max_length=60, blank=True, null=True)
    picture = models.ImageField(upload_to='profile_pictures/%y/%m/%d/', default='default.png', null=True)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, related_name='users')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='employees')
    date_of_joining = models.DateTimeField(_("date joined"), default=now)
    is_active = models.BooleanField(default=True)
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')

    # Override groups and user_permissions to avoid conflicts
    groups = models.ManyToManyField(
        Group,
        related_name='custom_user_groups',
        blank=True,
        help_text=_('The groups this user belongs to. A user will get all permissions granted to each of their groups.'),
        verbose_name=_('groups'),
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='custom_user_permissions',
        blank=True,
        help_text=_('Specific permissions for this user.'),
        verbose_name=_('user permissions'),
    )

    username_validator = ASCIIUsernameValidator()
    objects = UserManager()

    @property
    def get_full_name(self):
        full_name = self.username
        if self.first_name and self.last_name:
            full_name = self.first_name + " " + self.last_name
        return full_name

    def __str__(self):
        return '{} ({})'.format(self.username, self.get_full_name)

    def get_picture(self):
        try:
            return self.picture.url
        except:
            no_picture = settings.MEDIA_URL + 'default.png'
            return no_picture

    def get_absolute_url(self):
        return reverse('profile_single', kwargs={'id': self.id})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            img = Image.open(self.picture.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.picture.path)
        except:
            pass

    def delete(self, *args, **kwargs):
        if self.picture and self.picture.name != 'default.png':
            self.picture.delete(save=False)
        super().delete(*args, **kwargs)


class StaffUser(models.Model):
    """
    Represents a detailed profile for internal staff members.
    When a StaffUser is created, an EmployeeProfile and User are also created.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    emergency_contact = models.CharField(max_length=60, blank=True, null=True)
    date_of_birth = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.user.department.name if self.user.department else 'No Department'}"
