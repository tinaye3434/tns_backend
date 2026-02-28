from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import AllowanceSerializer, ApprovalStageSerializer, EmployeeSerializer, ClaimsSerializer, ClaimLineSerializer
from .models import (
    Allowance,
    ApprovalStage,
    Employee,
    Claim,
    ClaimLine,
    Department,
    Position,
    Grade,
    Gender,
    TnsClassifications,
    Status,
)


# Create your views here.

class AllowanceView(viewsets.ModelViewSet):
    serializer_class = AllowanceSerializer
    queryset = Allowance.objects.all()


class ApprovalStageView(viewsets.ModelViewSet):
    serializer_class = ApprovalStageSerializer
    queryset = ApprovalStage.objects.all()


class EmployeeView(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    queryset = Employee.objects.all()


class ClaimView(viewsets.ModelViewSet):
    serializer_class = ClaimsSerializer
    queryset = Claim.objects.all()


class ClaimLineView(viewsets.ModelViewSet):
    serializer_class = ClaimLineSerializer
    queryset = ClaimLine.objects.all()


def _choice_list(enum_class):
    return [{"value": value, "label": label} for value, label in enum_class.choices]


@api_view(['GET'])
def enums_view(request):
    return Response(
        {
            "department": _choice_list(Department),
            "position": _choice_list(Position),
            "grade": _choice_list(Grade),
            "gender": _choice_list(Gender),
            "tns_classification": _choice_list(TnsClassifications),
            "status": _choice_list(Status),
        }
    )
