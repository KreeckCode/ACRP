from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
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

# — LearnerProfile CRUD — #
@login_required
@permission_required('student.add_learnerprofile', raise_exception=True)
def learner_create(request):
    form = LearnerProfileForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request,'Learner created.')
        return redirect('student:learner_list')
    return render(request,'student/learner_form.html',{'form':form})

@login_required
@permission_required('student.view_learnerprofile', raise_exception=True)
def learner_list(request):
    qs = LearnerProfile.objects.all()
    return render(request,'student/learner_list.html',{'learners':qs})

@login_required
@permission_required('student.view_learnerprofile', raise_exception=True)
def learner_detail(request, pk):
    obj = get_object_or_404(LearnerProfile, pk=pk)
    return render(request,'student/learner_detail.html',{'learner':obj})

@login_required
@permission_required('student.change_learnerprofile', raise_exception=True)
def learner_update(request, pk):
    obj = get_object_or_404(LearnerProfile, pk=pk)
    form = LearnerProfileForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request,'Learner updated.')
        return redirect('student:learner_detail', pk=pk)
    return render(request,'student/learner_form.html',{'form':form,'update':True})

@login_required
@permission_required('student.delete_learnerprofile', raise_exception=True)
def learner_delete(request, pk):
    obj = get_object_or_404(LearnerProfile, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request,'Learner deleted.')
        return redirect('student:learner_list')
    return render(request,'student/learner_confirm_delete.html',{'learner':obj})

# — AcademicHistory CRUD — #
@login_required
@permission_required('student.add_academichistory', raise_exception=True)
def academic_create(request, learner_pk):
    learner = get_object_or_404(LearnerProfile, pk=learner_pk)
    form    = AcademicHistoryForm(request.POST or None)
    if form.is_valid():
        ah = form.save(commit=False)
        ah.learner = learner
        ah.save()
        messages.success(request,'Academic record added.')
        return redirect('student:learner_detail', pk=learner_pk)
    return render(request,'student/academic_form.html',{'form':form,'learner':learner})

# ... repeat list/detail/update/delete for AcademicHistory, Enrollment, CPD, CPDHistory, Affiliation, DocumentType, LearnerDocument
# For brevity, follow the same pattern as LearnerProfile above, adjusting the model, form, and permissions.
