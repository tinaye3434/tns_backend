from rest_framework.views import exception_handler
from rest_framework.response import Response


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    return Response(
        {
            "error": exc.__class__.__name__,
            "status_code": response.status_code,
            "detail": response.data,
        },
        status=response.status_code,
        headers=getattr(response, "headers", None),
    )
