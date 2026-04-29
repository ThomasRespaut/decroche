import re

from django.core.exceptions import ValidationError

E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


def validate_e164_phone(value: str) -> None:
    """Validate an international phone number in E.164 format."""
    if not value:
        return
    if not E164_REGEX.match(value):
        raise ValidationError(
            "Le numéro doit être au format E.164 (exemple: +33123456789)."
        )
