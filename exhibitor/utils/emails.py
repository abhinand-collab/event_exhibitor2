from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

def send_pending_reminder_email(attendee):
    subject = f"Action Required: Complete Your Registration for {attendee.event.name}"
    
    context = {
        "attendee": attendee,
        "event": attendee.event,
        "confirm_url": f"{settings.FRONTEND_URL}/register/{attendee.invite_token}/",
    }
    
    html_message = render_to_string("emails/pending_reminder.html", context)
    plain_message = render_to_string("emails/pending_reminder.txt", context)
    
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[attendee.email],
        html_message=html_message,
        fail_silently=False,
    )
