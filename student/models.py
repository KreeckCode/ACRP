from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from providers.models import Qualification

User = get_user_model()

class LearnerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='learner_profile')
    provider = models.OneToOneField('providers.Provider', null=True, blank=True, on_delete=models.CASCADE, related_name='learners')
    id_number          = models.CharField(max_length=50, unique=True)
    date_of_birth      = models.DateField()
    gender             = models.CharField(max_length=10, choices=[('M','Male'),('F','Female')])
    phone              = models.CharField(max_length=50)
    email              = models.EmailField()
    address            = models.TextField()
    nationality        = models.CharField(max_length=100)
    primary_language   = models.CharField(max_length=50)
    emergency_name     = models.CharField(max_length=100)
    emergency_relation = models.CharField(max_length=50)
    emergency_phone    = models.CharField(max_length=50)
    status             = models.CharField(
        max_length=10,
        choices=[('ENROLLED','Enrolled'),('GRADUATED','Graduated'),('WITHDRAWN','Withdrawn')],
        default='ENROLLED'
    )
    verification_status= models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('provider','id_number')

    def __str__(self):
        return f"{self.user.get_full_name} ({self.id_number})"


class AcademicHistory(models.Model):
    learner           = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='academics', db_index=True)
    institution_name  = models.CharField(max_length=200)
    qualification_name= models.CharField(max_length=200)
    completion_date   = models.DateField()
    grade_or_result   = models.CharField(max_length=50)
    certificate_file  = models.FileField(upload_to='learner/academics/', blank=True, null=True)
    verification_status= models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )

    def __str__(self):
        return f"{self.institution_name} – {self.qualification_name}"


class LearnerQualificationEnrollment(models.Model):
    learner          = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='enrollments')
    qualification = models.ForeignKey(Qualification, on_delete=models.CASCADE, related_name='enrollments')

    enrolled_date     = models.DateField()
    completion_date   = models.DateField(blank=True, null=True)
    status            = models.CharField(
        max_length=12,
        choices=[('IN_PROGRESS','In Progress'),('COMPLETED','Completed'),('CANCELLED','Cancelled')],
        default='IN_PROGRESS'
    )
    verification_status= models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        unique_together = ('learner', 'qualification')

    def __str__(self):
        return f"{self.learner.id_number} → {self.qualification.name}"


class CPDEvent(models.Model):
    date           = models.DateField()
    delivery_type  = models.CharField(max_length=10, choices=[('ONLINE','Online'),('ONSITE','Onsite'),('HYBRID','Hybrid')])
    topics         = models.CharField(max_length=200)
    presenters     = models.ManyToManyField(User, related_name='cpd_presented')
    default_points = models.DecimalField(max_digits=4, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"{self.date} | {self.topics}"


class CPDHistory(models.Model):
    learner            = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='cpd_history')
    event              = models.ForeignKey(CPDEvent, on_delete=models.CASCADE, related_name='histories')
    date_attended      = models.DateField()
    points_awarded     = models.DecimalField(max_digits=4, decimal_places=2)
    verification_status= models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"{self.learner.id_number} – {self.event.topics}"


class LearnerAffiliation(models.Model):
    learner           = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='affiliations')
    organization_name = models.CharField(max_length=200)
    affiliation_code  = models.CharField(max_length=50, blank=True, null=True)
    affiliation_date  = models.DateField()
    document          = models.FileField(upload_to='learner/affiliations/')
    verification_status= models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )

    def __str__(self):
        return f"{self.organization_name} ({self.learner.id_number})"


class DocumentType(models.Model):
    code        = models.CharField(max_length=20, unique=True)
    description = models.CharField(max_length=200)

    def __str__(self):
        return self.code


class LearnerDocument(models.Model):
    learner       = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='documents')
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    file          = models.FileField(upload_to='learner/documents/')
    uploaded_at   = models.DateTimeField(auto_now_add=True)
    verification_status= models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )
    reviewed_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    review_notes  = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.document_type.code} – {self.learner.id_number}"
