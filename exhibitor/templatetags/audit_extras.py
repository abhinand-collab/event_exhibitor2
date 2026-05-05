from django import template
from exhibitor.models import Event, Exhibitor

register = template.Library()

@register.filter
def event_name(event_id):
    if not event_id:
        return "None"
    try:
        return Event.objects.get(id=event_id).name
    except (Event.DoesNotExist, ValueError, TypeError):
        return event_id

@register.filter
def exhibitor_name(exhibitor_id):
    if not exhibitor_id:
        return "None"
    try:
        return Exhibitor.objects.get(id=exhibitor_id).company_name
    except (Exhibitor.DoesNotExist, ValueError, TypeError):
        return exhibitor_id