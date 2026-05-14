from django.urls import path
from .views import (
    index, Login, Logout, manuals, create_single_badge, 
    bulk_upload_save, registration_list, get_bulk_headers, 
    get_bulk_preview, validate_bulk_row, validate_bulk_batch,
    bulk_task_status, get_attendee, 
    update_attendee, delete_attendee, export_registrations, 
    send_invitations, register_attendee, 
    attendee_audit_logs, task_status_invitation, badge_email_status
)

urlpatterns = [
    path('', index, name="home"),
    path('api/registrations/', registration_list, name="registration_list"),
    path('login/', Login, name="login"),
    path('logout/', Logout, name="logout"),
    path('manuals/', manuals, name="manuals"),
    path("badge/create/", create_single_badge, name="create_single_badge"),
    
    # Bulk Upload (New backend driven)
    path('api/bulk-upload/headers/', get_bulk_headers, name="get_bulk_headers"),
    path('api/bulk-upload/preview/', get_bulk_preview, name="get_bulk_preview"),
    path('api/bulk-upload/validate-row/', validate_bulk_row, name="validate_bulk_row"),
    path('api/bulk-upload/validate-batch/', validate_bulk_batch, name="validate_bulk_batch"),
    path("bulk-upload-save/", bulk_upload_save, name="bulk_upload_save"),
    
    path("bulk-task-status/<str:task_id>/", bulk_task_status, name="bulk_task_status"),
    path('get-attendee/<int:attendee_id>/', get_attendee, name='get_attendee'),
    path('update-attendee/<int:attendee_id>/', update_attendee, name='update_attendee'),
    path('delete-attendee/<int:attendee_id>/', delete_attendee, name='delete_attendee'),
    path("export-registrations/", export_registrations, name="export_registrations"),
    path('send-invitations/', send_invitations, name='send_invitations'),
    path("register/<uuid:token>/", register_attendee, name="register_attendee"),
    path("attendee/<int:attendee_id>/logs/", attendee_audit_logs, name="attendee_audit_logs"),
    path("task-status-invitation/<str:task_id>/", task_status_invitation, name="task_status"),
    path(
        "badge-email-status/<str:task_id>/",
        badge_email_status,
        name="badge_email_status",
    ),
]
