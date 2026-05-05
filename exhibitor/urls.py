from django.urls import path
from .views import index,Login,create_single_badge,bulk_upload_preview,bulk_upload_save,validate_email
from .views import get_columns,bulk_update_session,bulk_task_status,get_attendee,update_attendee,delete_attendee
from .views import export_registrations,send_invitations,register_attendee,get_existing_emails,attendee_audit_logs

urlpatterns=[
    path('',index,name="home"),
    path('login/',Login,name="login"),
    path("badge/create/", create_single_badge, name="create_single_badge"),
    path("bulk-upload-preview/", bulk_upload_preview, name="bulk_upload_preview"),
    path("bulk-upload-save/", bulk_upload_save, name="bulk_upload_save"),
    path("validate-email/", validate_email, name="validate_email"),
    path("get-columns/",get_columns,name="get_columns"),
    path('bulk-update-session/', bulk_update_session, name='bulk_update_session'),
    path("bulk-task-status/<str:task_id>/", bulk_task_status, name="bulk_task_status"),
    path('get-attendee/<int:attendee_id>/',    get_attendee,    name='get_attendee'),
    path('update-attendee/<int:attendee_id>/', update_attendee, name='update_attendee'),
    path('delete-attendee/<int:attendee_id>/', delete_attendee, name='delete_attendee'),
    path("export-registrations/", export_registrations, name="export_registrations"),
    path('send-invitations/', send_invitations, name='send_invitations'),
    path("register/<uuid:token>/", register_attendee,name="register_attendee"),
    path('get-existing-emails/', get_existing_emails, name='get_existing_emails'),
    path("attendee/<int:attendee_id>/logs/", attendee_audit_logs, name="attendee_audit_logs"),
]