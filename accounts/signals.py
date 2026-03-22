from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User, Profile
from agents.models import AgentSettings


@receiver(post_save, sender=User)
def create_user_related_objects(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        AgentSettings.objects.create(user=instance)