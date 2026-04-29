from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

from core.validators import validate_e164_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("L'adresse email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Le superuser doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Le superuser doit avoir is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Profile(models.Model):
    ACTIVITY_CHOICES = [
        ("restaurant", "Restaurant"),
        ("medical", "Cabinet médical"),
        ("salon", "Salon / Beauté"),
        ("immobilier", "Immobilier"),
        ("artisan", "Artisan"),
        ("autre", "Autre"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    phone = models.CharField(max_length=30, blank=True, validators=[validate_e164_phone])
    company_name = models.CharField(max_length=255, blank=True)
    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_CHOICES,
        blank=True,
    )

    business_email = models.EmailField(blank=True)

    # On harmonise avec le form
    website_url = models.URLField(blank=True)

    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=120, default="France", blank=True)

    business_description = models.TextField(blank=True)
    opening_hours = models.TextField(blank=True)

    # Notes internes / consignes métier
    extra_notes = models.TextField(blank=True)

    logo = models.ImageField(upload_to="logos/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.company_name or self.user.email