from django.contrib import admin

from .models import AbonnementPush, Notification, PreferenceNotification

admin.site.register(Notification)
admin.site.register(AbonnementPush)
admin.site.register(PreferenceNotification)
