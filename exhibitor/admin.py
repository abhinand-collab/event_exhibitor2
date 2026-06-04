from django.contrib import admin
from .models import Event,Exhibitor,Attendee,Badge,User,ComplimentaryInvitation
from django.contrib.auth.admin import UserAdmin



# Register your models here.
admin.site.register(User,UserAdmin)
admin.site.register(Event)
admin.site.register(Exhibitor)
# admin.site.register(Attendee)
admin.site.register(Badge)
admin.site.register(ComplimentaryInvitation)

@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "email",
        "attendee_type",
        "status",
        "invite_token",   # 👈 add here
    )