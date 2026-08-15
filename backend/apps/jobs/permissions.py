from rest_framework.permissions import BasePermission
from django.conf import settings


class InternalTokenPermission(BasePermission):
    """Require Authorization: Bearer <INTERNAL_API_TOKEN>."""

    def has_permission(self, request, view) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:].strip()
        expected = getattr(settings, "INTERNAL_API_TOKEN", "")
        return bool(expected) and token == expected
