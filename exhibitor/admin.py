from django.contrib import admin
from .models import Event,Exhibitor,Attendee,Badge,User
from django.contrib.auth.admin import UserAdmin



# Register your models here.
admin.site.register(User,UserAdmin)
admin.site.register(Event)
admin.site.register(Exhibitor)
admin.site.register(Attendee)
admin.site.register(Badge)