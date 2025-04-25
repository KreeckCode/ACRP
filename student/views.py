from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.utils import timezone

from .models import (
    LearnerProfile, AcademicHistory,
    LearnerQualificationEnrollment,
    CPDEvent, CPDHistory,
    LearnerAffiliation, DocumentType,
    LearnerDocument
)
from .forms import (
    LearnerProfileForm, AcademicHistoryForm,
    EnrollmentForm, CPDEventForm, CPDHistoryForm,
    AffiliationForm, DocumentTypeForm, LearnerDocumentForm
)


# LearnerProfile CRUD

@login_required
@permission_required('student.add_learnerprofile', raise_exception=True)
def learner_create(request):
    form = LearnerProfileForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Learner profile created.')
        return redirect('student:learner_list')
    return render(request, 'student/learner_form.html', {'form': form})

@login_required
@permission_required('student.view_learnerprofile', raise_exception=True)
def learner_list(request):
    learners = LearnerProfile.objects.all()
    return render(request, 'student/learner_list.html', {'learners': learners})

@login_required
@permission_required('student.view_learnerprofile', raise_exception=True)
def learner_detail(request, pk):
    learner = get_object_or_404(LearnerProfile, pk=pk)
    return render(request, 'student/learner_detail.html', {'learner': learner})

@login_required
@permission_required('student.change_learnerprofile', raise_exception=True)
def learner_update(request, pk):
    learner = get_object_or_404(LearnerProfile, pk=pk)
    form = LearnerProfileForm(request.POST or None, request.FILES or None, instance=learner)
    if form.is_valid():
        form.save()
        messages.success(request, 'Learner profile updated.')
        return redirect('student:learner_detail', pk=pk)
    return render(request, 'student/learner_form.html', {'form': form, 'update': True})

@login_required
@permission_required('student.delete_learnerprofile', raise_exception=True)
def learner_delete(request, pk):
    learner = get_object_or_404(LearnerProfile, pk=pk)
    if request.method == 'POST':
        learner.delete()
        messages.success(request, 'Learner profile deleted.')
        return redirect('student:learner_list')
    return render(request, 'student/learner_confirm_delete.html', {'learner': learner})


# AcademicHistory CRUD (nested)

@login_required
@permission_required('student.view_academichistory', raise_exception=True)
def academic_list(request, learner_pk):
    learner  = get_object_or_404(LearnerProfile, pk=learner_pk)
    records  = learner.academics.all()
    return render(request, 'student/academic_list.html', {'learner': learner, 'records': records})

@login_required
@permission_required('student.add_academichistory', raise_exception=True)
def academic_create(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    form    = AcademicHistoryForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        ah = form.save(commit=False)
        ah.learner = learner
        ah.save()
        messages.success(request, 'Academic history added.')
        return redirect('student:academic_list', learner_pk=learner_pk)
    return render(request, 'student/academic_form.html', {'form': form, 'learner': learner})

@login_required
@permission_required('student.change_academichistory', raise_exception=True)
def academic_update(request, learner_pk, pk):
    ah   = get_object_or_404(AcademicHistory, pk=pk, learner_id=learner_pk)
    form = AcademicHistoryForm(request.POST or None, request.FILES or None, instance=ah)
    if form.is_valid():
        form.save()
        messages.success(request, 'Academic history updated.')
        return redirect('student:academic_list', learner_pk=learner_pk)
    return render(request, 'student/academic_form.html', {'form': form, 'update': True, 'learner': ah.learner})

@login_required
@permission_required('student.delete_academichistory', raise_exception=True)
def academic_delete(request, learner_pk, pk):
    ah = get_object_or_404(AcademicHistory, pk=pk, learner_id=learner_pk)
    if request.method == 'POST':
        ah.delete()
        messages.success(request, 'Academic history removed.')
        return redirect('student:academic_list', learner_pk=learner_pk)
    return render(request, 'student/academic_confirm_delete.html', {'record': ah})


# Enrollment CRUD (nested)

@login_required
@permission_required('student.view_learnerqualificationenrollment', raise_exception=True)
def enrollment_list(request, learner_pk):
    learner    = get_object_or_404(LearnerProfile, pk=learner_pk)
    enrollments= learner.enrollments.all()
    return render(request, 'student/enrollment_list.html', {'learner': learner, 'enrollments': enrollments})

@login_required
@permission_required('student.add_learnerqualificationenrollment', raise_exception=True)
def enrollment_create(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    form    = EnrollmentForm(request.POST or None)
    if form.is_valid():
        en = form.save(commit=False)
        en.learner = learner
        en.save()
        messages.success(request, 'Enrollment added.')
        return redirect('student:enrollment_list', learner_pk=learner_pk)
    return render(request, 'student/enrollment_form.html', {'form': form, 'learner': learner})

@login_required
@permission_required('student.change_learnerqualificationenrollment', raise_exception=True)
def enrollment_update(request, learner_pk, pk):
    en   = get_object_or_404(LearnerQualificationEnrollment, pk=pk, learner_id=learner_pk)
    form = EnrollmentForm(request.POST or None, instance=en)
    if form.is_valid():
        form.save()
        messages.success(request, 'Enrollment updated.')
        return redirect('student:enrollment_list', learner_pk=learner_pk)
    return render(request, 'student/enrollment_form.html', {'form': form, 'update': True, 'learner': en.learner})

@login_required
@permission_required('student.delete_learnerqualificationenrollment', raise_exception=True)
def enrollment_delete(request, learner_pk, pk):
    en = get_object_or_404(LearnerQualificationEnrollment, pk=pk, learner_id=learner_pk)
    if request.method == 'POST':
        en.delete()
        messages.success(request, 'Enrollment removed.')
        return redirect('student:enrollment_list', learner_pk=learner_pk)
    return render(request, 'student/enrollment_confirm_delete.html', {'enrollment': en})


# CPDEvent CRUD (global)

@login_required
@permission_required('student.add_cpdevent', raise_exception=True)
def cpd_event_create(request):
    form = CPDEventForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'CPD Event created.')
        return redirect('student:cpd_event_list')
    return render(request, 'student/cpd_event_form.html', {'form': form})

@login_required
@permission_required('student.view_cpdevent', raise_exception=True)
def cpd_event_list(request):
    events = CPDEvent.objects.all()
    return render(request, 'student/cpd_event_list.html', {'events': events})

@login_required
@permission_required('student.view_cpdevent', raise_exception=True)
def cpd_event_detail(request, pk):
    ev = get_object_or_404(CPDEvent, pk=pk)
    return render(request, 'student/cpd_event_detail.html', {'event': ev})

@login_required
@permission_required('student.change_cpdevent', raise_exception=True)
def cpd_event_update(request, pk):
    ev   = get_object_or_404(CPDEvent, pk=pk)
    form = CPDEventForm(request.POST or None, instance=ev)
    if form.is_valid():
        form.save()
        messages.success(request, 'CPD Event updated.')
        return redirect('student:cpd_event_detail', pk=pk)
    return render(request, 'student/cpd_event_form.html', {'form': form, 'update': True})

@login_required
@permission_required('student.delete_cpdevent', raise_exception=True)
def cpd_event_delete(request, pk):
    ev = get_object_or_404(CPDEvent, pk=pk)
    if request.method == 'POST':
        ev.delete()
        messages.success(request, 'CPD Event deleted.')
        return redirect('student:cpd_event_list')
    return render(request, 'student/cpd_event_confirm_delete.html', {'event': ev})


# CPDHistory CRUD (nested)

@login_required
@permission_required('student.view_cpdhistory', raise_exception=True)
def cpd_history_list(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    history = learner.cpd_history.all()
    return render(request, 'student/cpd_history_list.html', {'learner': learner, 'history': history})

@login_required
@permission_required('student.add_cpdhistory', raise_exception=True)
def cpd_history_create(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    form    = CPDHistoryForm(request.POST or None)
    if form.is_valid():
        ch = form.save(commit=False)
        ch.learner = learner
        ch.save()
        messages.success(request, 'CPD record added.')
        return redirect('student:cpd_history_list', learner_pk=learner_pk)
    return render(request, 'student/cpd_history_form.html', {'form': form, 'learner': learner})

@login_required
@permission_required('student.change_cpdhistory', raise_exception=True)
def cpd_history_update(request, learner_pk, pk):
    ch   = get_object_or_404(CPDHistory, pk=pk, learner_id=learner_pk)
    form = CPDHistoryForm(request.POST or None, instance=ch)
    if form.is_valid():
        form.save()
        messages.success(request, 'CPD record updated.')
        return redirect('student:cpd_history_list', learner_pk=learner_pk)
    return render(request, 'student/cpd_history_form.html', {'form': form, 'update': True, 'learner': ch.learner})

@login_required
@permission_required('student.delete_cpdhistory', raise_exception=True)
def cpd_history_delete(request, learner_pk, pk):
    ch = get_object_or_404(CPDHistory, pk=pk, learner_id=learner_pk)
    if request.method == 'POST':
        ch.delete()
        messages.success(request, 'CPD record removed.')
        return redirect('student:cpd_history_list', learner_pk=learner_pk)
    return render(request, 'student/cpd_history_confirm_delete.html', {'record': ch})


# Affiliation CRUD (nested)

@login_required
@permission_required('student.view_learneraffiliation', raise_exception=True)
def affiliation_list(request, learner_pk):
    learner     = get_object_or_404(LearnerProfile, pk=learner_pk)
    affiliations = learner.affiliations.all()
    return render(request, 'student/affiliation_list.html', {'learner': learner, 'affiliations': affiliations})

@login_required
@permission_required('student.add_learneraffiliation', raise_exception=True)
def affiliation_create(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    form    = AffiliationForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        af = form.save(commit=False)
        af.learner = learner
        af.save()
        messages.success(request, 'Affiliation added.')
        return redirect('student:affiliation_list', learner_pk=learner_pk)
    return render(request, 'student/affiliation_form.html', {'form': form, 'learner': learner})

@login_required
@permission_required('student.change_learneraffiliation', raise_exception=True)
def affiliation_update(request, learner_pk, pk):
    af   = get_object_or_404(LearnerAffiliation, pk=pk, learner_id=learner_pk)
    form = AffiliationForm(request.POST or None, request.FILES or None, instance=af)
    if form.is_valid():
        form.save()
        messages.success(request, 'Affiliation updated.')
        return redirect('student:affiliation_list', learner_pk=learner_pk)
    return render(request, 'student/affiliation_form.html', {'form': form, 'update': True, 'learner': af.learner})

@login_required
@permission_required('student.delete_learneraffiliation', raise_exception=True)
def affiliation_delete(request, learner_pk, pk):
    af = get_object_or_404(LearnerAffiliation, pk=pk, learner_id=learner_pk)
    if request.method == 'POST':
        af.delete()
        messages.success(request, 'Affiliation removed.')
        return redirect('student:affiliation_list', learner_pk=learner_pk)
    return render(request, 'student/affiliation_confirm_delete.html', {'affiliation': af})


# DocumentType CRUD (global)

@login_required
@permission_required('student.view_documenttype', raise_exception=True)
def document_type_list(request):
    types = DocumentType.objects.all()
    return render(request, 'student/document_type_list.html', {'types': types})

@login_required
@permission_required('student.add_documenttype', raise_exception=True)
def document_type_create(request):
    form = DocumentTypeForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Document type created.')
        return redirect('student:document_type_list')
    return render(request, 'student/document_type_form.html', {'form': form})

@login_required
@permission_required('student.change_documenttype', raise_exception=True)
def document_type_update(request, pk):
    dt   = get_object_or_404(DocumentType, pk=pk)
    form = DocumentTypeForm(request.POST or None, instance=dt)
    if form.is_valid():
        form.save()
        messages.success(request, 'Document type updated.')
        return redirect('student:document_type_list')
    return render(request, 'student/document_type_form.html', {'form': form, 'update': True})

@login_required
@permission_required('student.delete_documenttype', raise_exception=True)
def document_type_delete(request, pk):
    dt = get_object_or_404(DocumentType, pk=pk)
    if request.method == 'POST':
        dt.delete()
        messages.success(request, 'Document type deleted.')
        return redirect('student:document_type_list')
    return render(request, 'student/document_type_confirm_delete.html', {'type': dt})


# LearnerDocument CRUD (nested, with review)

@login_required
@permission_required('student.view_learnerdocument', raise_exception=True)
def learner_document_list(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    docs    = learner.documents.all()
    return render(request, 'student/document_list.html', {'learner': learner, 'documents': docs})

@login_required
@permission_required('student.add_learnerdocument', raise_exception=True)
def learner_document_upload(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    form    = LearnerDocumentForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        ld = form.save(commit=False)
        ld.learner = learner
        ld.save()
        messages.success(request, 'Document uploaded; pending approval.')
        return redirect('student:learner_document_list', learner_pk=learner_pk)
    return render(request, 'student/document_form.html', {'form': form, 'learner': learner})

@login_required
@permission_required('student.change_learnerdocument', raise_exception=True)
def learner_document_review(request, pk):
    doc = get_object_or_404(LearnerDocument, pk=pk)
    if request.method == 'POST':
        doc.status       = request.POST.get('status')
        doc.review_notes = request.POST.get('review_notes','')
        doc.reviewed_by  = request.user
        doc.reviewed_at  = timezone.now()
        doc.save()
        messages.success(request, 'Document review saved.')
        return redirect('student:learner_document_list', learner_pk=doc.learner.pk)
    return render(request, 'student/document_review.html', {'doc': doc})
