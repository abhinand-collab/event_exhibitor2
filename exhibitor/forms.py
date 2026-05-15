from django import forms
from .models import Attendee
import re

# TICKET_TYPE_CHOICES = [
#     ("", "Select Ticket Type"),
#     ("VIP", "VIP Pass"),
#     ("EXHIBITOR", "Exhibitor Pass"),
#     ("VISITOR", "Visitor Pass"),
# ]

# CreateBadgeForm is no longer used for main attendee operations.
# Validation has been moved to SingleAttendeeSerializer in serializers.py.

class CreateBadgeForm(forms.Form):
    """
    Deprecated. Kept as empty to avoid import errors during transition
    but views should now use SingleAttendeeSerializer.
    """
    pass
