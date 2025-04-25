from django.db import models
from django.conf import settings

class LearnerProfile(models.Model):
    user              = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learner_profile')
    id_number         = models.CharField(max_length=50, unique=True)
    date_of_birth     = models.DateField()
    gender            = models.CharField(max_length=10, choices=[('M','Male'),('F','Female'),('O','Other')])
    phone             = models.CharField(max_length=50)
    email             = models.EmailField()
    address           = models.TextField()
    nationality       = models.CharField(max_length=100)
    primary_language  = models.CharField(max_length=50)
    emergency_name    = models.CharField(max_length=100)
    emergency_relation= models.CharField(max_length=50)
    emergency_phone   = models.CharField(max_length=50)
    status            = models.CharField(
        max_length=10,
        choices=[('ENROLLED','Enrolled'),('GRADUATED','Graduated'),('WITHDRAWN','Withdrawn')],
        default='ENROLLED'
    )

    def __str__(self):
        return f"{self.user.get_full_name} ({self.id_number})"


class AcademicHistory(models.Model):
    learner           = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='academics')
    institution_name  = models.CharField(max_length=200)
    qualification_name= models.CharField(max_length=200)
    completion_date   = models.DateField()
    grade_or_result   = models.CharField(max_length=50)
    certificate_file  = models.FileField(upload_to='learner/academics/', blank=True, null=True)


class LearnerQualificationEnrollment(models.Model):
    learner         = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='enrollments')
    qualification    = models.ForeignKey('provider.Qualification', on_delete=models.CASCADE)
    enrolled_date    = models.DateField()
    completion_date  = models.DateField(blank=True, null=True)
    status           = models.CharField(
        max_length=12,
        choices=[('IN_PROGRESS','In Progress'),('COMPLETED','Completed'),('CANCELLED','Cancelled')],
        default='IN_PROGRESS'
    )


class CPDEvent(models.Model):
    date           = models.DateField()
    delivery_type  = models.CharField(max_length=10, choices=[('ONLINE','Online'),('ONSITE','Onsite'),('HYBRID','Hybrid')])
    topics         = models.CharField(max_length=200)
    presenters     = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='cpd_presented')
    default_points = models.DecimalField(max_digits=4, decimal_places=2)


class CPDHistory(models.Model):
    learner             = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='cpd_history')
    event               = models.ForeignKey(CPDEvent, on_delete=models.CASCADE)
    date_attended       = models.DateField()
    points_awarded      = models.DecimalField(max_digits=4, decimal_places=2)
    verification_status = models.CharField(
        max_length=8,
        choices=[('PENDING','Pending'),('VERIFIED','Verified'),('REJECTED','Rejected')],
        default='PENDING'
    )


class LearnerAffiliation(models.Model):
    learner           = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name='affiliations')
    organization_name = models.CharField(max_length=200)
    affiliation_code  = models.CharField(max_length=50, blank=True, null=True)
    affiliation_date  = models.DateField()
    document          = models.FileField(upload_to='learner/affiliations/')
    status            = models.CharField(
        max_length=8,
        choices=[('VERIFIED','Verified'),('INVALID','Invalid'),('PENDING','Pending')],
        default='PENDING'
    )


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
    status        = models.CharField(
        max_length=10,
        choices=[('PENDING','Pending'),('APPROVED','Approved'),('REJECTED','Rejected')],
        default='PENDING'
    )
    reviewed_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    review_notes  = models.TextField(blank=True, null=True)
