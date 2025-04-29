from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType       # for GenericForeignKey
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

# — Generic Document upload for any affiliation type
class Document(models.Model):
    DOCUMENT_CATEGORIES = [
        ('supporting', 'Supporting Document'),
        ('payment', 'Proof of Payment'),
        ('qualification', 'Qualification'),
    ]

    content_type   = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id      = models.PositiveBigIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')  # link to any affiliation instance 
    category       = models.CharField(max_length=20, choices=DOCUMENT_CATEGORIES)
    file           = models.FileField(upload_to='enrollments/docs/%Y/%m/%d/')
    uploaded_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_category_display()} for {self.content_object}"

# — ASSOCIATED AFFILIATION —
class AssociatedAffiliation(models.Model):
    # Approval workflow (hidden from ModelForms via editable=False)
    approved       = models.BooleanField(default=False, editable=False)
    approved_at    = models.DateTimeField(null=True, blank=True, editable=False)
    approved_by    = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_associated_affiliations', editable=False)
    created_user   = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='associated_enrollments', editable=False)

    GENDER_CHOICES = [('male','Male'),('female','Female')]
    TITLE_CHOICES = [('Mr', 'Mr'), ('Mrs', 'Mrs'), ('Miss', 'Miss')]
    title           = models.CharField(max_length=20, choices=TITLE_CHOICES)
    gender          = models.CharField(max_length=10, choices=GENDER_CHOICES)
    surname         = models.CharField(max_length=50)
    initials        = models.CharField(max_length=10)
    disability      = models.CharField(max_length=100, blank=True, null=True)
    first_name      = models.CharField(max_length=150, blank=True)
    last_name       = models.CharField(max_length=150, blank=True)
    id_number       = models.CharField(max_length=20)
    race            = models.CharField(max_length=20)
    preferred_name  = models.CharField(max_length=50, blank=True)
    date_of_birth   = models.DateField()
    passport_number = models.CharField(max_length=30, blank=True)
    postal_address  = models.TextField(blank=True)
    street_address  = models.TextField(blank=True)
    postal_code     = models.CharField(max_length=10, blank=True)
    province        = models.CharField(max_length=50, blank=True)
    country         = models.CharField(max_length=50, default='South Africa')
    tel_work        = models.CharField(max_length=20, blank=True)
    tel_home        = models.CharField(max_length=20, blank=True)
    fax             = models.CharField(max_length=20, blank=True)
    cell            = models.CharField(max_length=20,blank=True)
    religious_affiliation = models.CharField(max_length=100, blank=True)
    email           = models.EmailField()
    website         = models.URLField(blank=True)

    highest_qualification    = models.CharField(max_length=200, blank=True)
    qualification_date       = models.DateField()
    qualification_institution = models.CharField(max_length=200)

    home_language   = models.CharField(max_length=50, blank=True)
    other_languages = models.CharField(max_length=100, blank=True)

    disciplinary_action      = models.BooleanField(default=False)
    disciplinary_description = models.TextField(blank=True)
    felony_conviction        = models.BooleanField(default=False)
    felony_description       = models.TextField(blank=True)

    occupation       = models.CharField(max_length=100, blank=True)
    work_description = models.TextField(blank=True)
    years_ministry   = models.PositiveIntegerField(default=0)
    months_ministry  = models.PositiveIntegerField(default=0)

    involved_pastoral    = models.BooleanField(default=False)
    registered_elsewhere = models.BooleanField(default=False)
    suitably_trained     = models.BooleanField(default=False)

    documents = GenericRelation(Document)

    def __str__(self):
        return f"AssociatedAffiliation({self.first_name} {self.last_name})"
