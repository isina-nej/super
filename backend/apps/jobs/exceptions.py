from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    return Response(
        {"detail": str(exc) or "خطای داخلی سرور"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
