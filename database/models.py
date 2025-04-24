from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from accounts.models import User


class Database(models.Model):
    name = models.CharField(max_length=40)
    description = models.TextField(max_length=300, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="owned_databases")
    is_public = models.BooleanField(default=False)
    is_protected = models.BooleanField(default=True)
    password = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.is_protected:
            self.password = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Entry(models.Model):
    database = models.ForeignKey(Database, on_delete=models.CASCADE, related_name="entries")
    
    class DatabaseType(models.TextChoices):
        PEOPLE = "People", _("People")
        PRODUCT = "Product", _("Product")
        ASSET = "Asset", _("Asset")

    database_type = models.CharField(
        max_length=50, choices=DatabaseType.choices, default=DatabaseType.PEOPLE
    )
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    email = models.EmailField(_("email address"), blank=True)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    date_of_birth = models.DateField(blank=True, null=True)
    grade = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.database.name}"
