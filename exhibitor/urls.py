from django.urls import path
from .views import (
    index, Login, Logout, manuals, create_single_badge, 
    bulk_upload_save, registration_list, get_bulk_headers, 
    get_bulk_preview, validate_bulk_row, validate_bulk_batch,
    bulk_task_status, get_attendee, 
    update_attendee, delete_attendee, bulk_delete_attendees, export_registrations, 
    send_invitations, register_attendee, 
    attendee_audit_logs, task_status_invitation,
    get_invitation_preview,validate_invitation_row,validate_invitation_batch,
    complimentary_invitations_page, complimentary_invitations_list, 
    create_complimentary_invitation, 
    create_personalized_invitation_link,
    send_complimentary_invitation_email, register_complimentary_attendee,
    get_invitation_usage_details,
    complimentary_attendee_logs,
    toggle_complimentary_link, bulk_toggle_complimentary_links,
    update_complimentary_link, bulk_update_complimentary_links
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

    # Invitations Bulk (New backend driven)
    path('api/invitations/headers/', get_bulk_headers, name="get_invitation_headers"), # Reuse get_bulk_headers
    path('api/invitations/preview/', get_invitation_preview, name="get_invitation_preview"),
    path('api/invitations/validate-row/', validate_invitation_row, name="validate_invitation_row"),
    path('api/invitations/validate-batch/', validate_invitation_batch, name="validate_invitation_batch"),
    
    path("bulk-task-status/<str:task_id>/", bulk_task_status, name="bulk_task_status"),
    path('get-attendee/<int:attendee_id>/', get_attendee, name='get_attendee'),
    path('update-attendee/<int:attendee_id>/', update_attendee, name='update_attendee'),
    path('delete-attendee/<int:attendee_id>/', delete_attendee, name='delete_attendee'),
    path('bulk-delete-attendees/', bulk_delete_attendees, name='bulk_delete_attendees'),
    path("export-registrations/", export_registrations, name="export_registrations"),
    path('send-invitations/', send_invitations, name='send_invitations'),
    path("register/<uuid:token>/", register_attendee, name="register_attendee"),
    
    # Complimentary Invitations
    path('complimentary-invitations/', complimentary_invitations_page, name="complimentary_invitations"),
    path('api/complimentary-invitations/', complimentary_invitations_list, name="complimentary_invitations_list"),
    path('api/complimentary/create/', create_complimentary_invitation, name="create_complimentary_invitation"),
    path('api/complimentary/create-personalized/', create_personalized_invitation_link, name="create_personalized_invitation_link"),
    path('api/complimentary/send-email/', send_complimentary_invitation_email, name="send_complimentary_invitation_email"),
    path('api/complimentary/toggle/', toggle_complimentary_link, name="toggle_complimentary_link"),
    path('api/complimentary/bulk-toggle/', bulk_toggle_complimentary_links, name="bulk_toggle_complimentary_links"),
    path('api/complimentary/update/', update_complimentary_link, name="update_complimentary_link"),
    path('api/complimentary/bulk-update/', bulk_update_complimentary_links, name="bulk_update_complimentary_links"),
    path('api/complimentary/usage/<int:invite_id>/', get_invitation_usage_details, name="get_invitation_usage_details"),
    path('api/complimentary/attendee/<int:attendee_id>/logs/', complimentary_attendee_logs, name="complimentary_attendee_logs"),
    path('register/complimentary/<uuid:token>/', register_complimentary_attendee, name="register_complimentary_attendee"),

    path("attendee/<int:attendee_id>/logs/", attendee_audit_logs, name="attendee_audit_logs"),
    path("task-status-invitation/<str:task_id>/", task_status_invitation, name="task_status"),
]
