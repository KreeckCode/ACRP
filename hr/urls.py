from django.urls import path
from . import views

urlpatterns = [
    # Employee Profile URLs
    path('employee_profiles/', views.employee_profile_list, name='employee_profile_list'),
    path('employee_profiles/create/', views.create_employee_profile, name='create_employee_profile'),
    path('employee_profiles/<int:profile_id>/update/', views.update_employee_profile, name='update_employee_profile'),
    path('employee_profiles/<int:profile_id>/detail/', views.employee_profile_detail, name='employee_profile_detail'),
    path("my-profile/", views.my_profile, name="my_profile"),

    # Employee Document URLs
    path('employee_profiles/<int:profile_id>/documents/create/', views.manage_employee_document, name='manage_employee_document'),
    path('employee_profiles/<int:profile_id>/documents/<int:document_id>/edit/', views.manage_employee_document, name='edit_employee_document'),

    # Employee Warning URLs
    path("warnings/", views.all_employee_warnings, name="all_employee_warnings"),
    path("employee_profiles/<int:profile_id>/warnings/", views.employee_warning_list, name="employee_warning_list"),
    path('employee_profiles/<int:profile_id>/warnings/<int:warning_id>/', views.employee_warning_detail, name='employee_warning_detail'),
    path('employee_warnings/create/', views.create_employee_warning, name='create_employee_warning'),
    path('employee_profiles/<int:profile_id>/warnings/<int:warning_id>/edit/', views.edit_employee_warning, name='edit_employee_warning'),
    path('employee_profiles/<int:profile_id>/warnings/<int:warning_id>/delete/', views.delete_employee_warning, name='delete_employee_warning'),


    #Folder-based navigation
    path('folders/', views.folder_list, name='folder_list'),
    path('folders/<int:folder_id>/', views.folder_detail, name='folder_detail'),
    path('folders/<int:parent_id>/create/', views.create_folder, name='create_subfolder'),
    path('folders/create/', views.create_folder, name='create_folder'),
    path('folders/<int:folder_id>/delete/', views.folder_delete, name='folder_delete'),

    # Documents
    path('documents/upload/', views.upload_document, name='upload_document'),
    path('documents/upload/<int:folder_id>/', views.upload_document, name='upload_document_folder'),
    path('documents/<int:document_id>/download/', views.document_download, name='document_download'),
    path('documents/<int:document_id>/delete/', views.document_delete, name='document_delete'),
    path('documents/<int:document_id>/share/', views.share_document, name='share_document'),


    # Document Request
    path('document-request/new/', views.create_document_request, name='create_document_request'),
    path('document-request/', views.document_request_list, name='document_request_list'),
    path('document-request/<int:request_id>/', views.document_request_detail, name='document_request_detail'),
    path('document-request/<int:request_id>/process/', views.process_document_request, name='process_document_request'),
    path('document-request/<int:request_id>/delete/', views.delete_document_request, name='delete_document_request'),
    path('share/download/<uuid:token>/', views.document_share_download, name='document_share_download'),


    # Public share link (no login required typically)
    path('shared/<uuid:token>/', views.document_share_view, name='document_share_view'),
    path('document-request/external/<uuid:token>/', views.external_document_request_view, name='external_document_request_view'),
    path('document-request/external/success/', views.external_document_request_success, name='external_document_request_success'),
    

    # Access logs
    path('documents/<int:document_id>/access_logs/', views.document_access_logs, name='document_access_logs'),

    
    path('library/', views.hr_document_list, name='hr_document_list'),
    path('files/create/', views.manage_hr_document, name='create_hr_document'),
    path('files/<int:document_id>/edit/', views.manage_hr_document, name='edit_hr_document'),
    path('files/<int:document_id>/access_logs/', views.document_access_logs, name='document_access_logs'),
    path('file/<int:document_id>/delete/', views.delete_hr_document, name='delete_hr_document'
    ),
    # Leave Request URLs
    path('leave_requests/', views.leave_request_list, name='leave_request_list'),
    path('leave_requests/create/', views.create_leave_request, name='create_leave_request'),
    path('leave_requests/<int:leave_request_id>/handle/', views.handle_leave_request, name='handle_leave_request'),

    # Leave Analytics
    path('leave_analytics/', views.leave_analytics_dashboard, name='leave_analytics_dashboard'),

    # Payslip Management
    path('payslips/', views.payslip_list, name='payslip_list'),
    path('payslips/<int:payslip_id>/view/', views.view_payslip, name='view_payslip'),
    #path('employee_documents/<int:document_id>/delete/', views.delete_employee_document, name='delete_employee_document'),

]
