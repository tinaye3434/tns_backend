from django.db import transaction
from rest_framework import status as drf_status, viewsets
from rest_framework.decorators import action, api_view
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
    queryset = ApprovalStage.objects.all().order_by('order', 'id')

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request):
        ids = request.data.get('ids')

        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "ids must be a non-empty list"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        try:
            ordered_ids = [int(stage_id) for stage_id in ids]
        except (TypeError, ValueError):
            return Response(
                {"detail": "ids must contain only integers"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        if len(set(ordered_ids)) != len(ordered_ids):
            return Response(
                {"detail": "ids must be unique"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        total_stages = ApprovalStage.objects.count()
        if len(ordered_ids) != total_stages:
            return Response(
                {"detail": "ids must include all approval stages"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            stages = list(
                ApprovalStage.objects.select_for_update().filter(id__in=ordered_ids)
            )
            if len(stages) != len(ordered_ids):
                return Response(
                    {"detail": "One or more stage IDs are invalid"},
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )

            stage_by_id = {stage.id: stage for stage in stages}
            for index, stage_id in enumerate(ordered_ids, start=1):
                stage_by_id[stage_id].order = index

            ApprovalStage.objects.bulk_update(stages, ['order'])

        return Response({"detail": "Approval stages reordered"})


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
