from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import Formateur


@receiver(post_delete, sender=Formateur)
def deactivate_user_on_formateur_delete(sender, instance, **kwargs):
    if instance.user:
        instance.user.is_active = False
        instance.user.save(update_fields=['is_active'])
