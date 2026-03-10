from django.db import transaction
import math
from datetime import timedelta
from rest_framework import status as drf_status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework import serializers
from .serializers import AllowanceSerializer, ApprovalStageSerializer, EmployeeSerializer, ClaimsSerializer, ClaimLineSerializer, LocationSerializer
from .models import (
    Allowance,
    ApprovalStage,
    Employee,
    Claim,
    ClaimLine,
    Location,
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

    def _distance_km(self, origin_name, destination_name):
        if not origin_name or not destination_name:
            return None
        origin = Location.objects.filter(name__iexact=origin_name).first()
        destination = Location.objects.filter(name__iexact=destination_name).first()
        if not origin or not destination:
            return None

        # Haversine formula
        radius_km = 6371.0
        lat1 = math.radians(origin.latitude)
        lon1 = math.radians(origin.longitude)
        lat2 = math.radians(destination.latitude)
        lon2 = math.radians(destination.longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        allowances = serializer.validated_data.pop('allowances', [])
        auto_distance = serializer.validated_data.pop('auto_distance', False)
        employee_alias = serializer.validated_data.pop('employee', None)
        total_allowances = serializer.validated_data.pop('total_allowances', None)

        if allowances and not isinstance(allowances, list):
            raise serializers.ValidationError({"allowances": "Must be a list of allowance objects."})

        if serializer.validated_data.get('employee_id') is None and employee_alias is not None:
            try:
                serializer.validated_data['employee_id'] = int(employee_alias)
            except (TypeError, ValueError):
                raise serializers.ValidationError({"employee": "Employee must be an integer id."})

        if serializer.validated_data.get('total') is None and total_allowances is not None:
            serializer.validated_data['total'] = total_allowances

        departure_date = serializer.validated_data.get('departure_date')
        return_date = serializer.validated_data.get('return_date')
        if serializer.validated_data.get('days') is None and departure_date and return_date:
            delta = return_date - departure_date
            if delta < timedelta(0):
                raise serializers.ValidationError({"return_date": "return_date must be after departure_date."})
            serializer.validated_data['days'] = max(1, delta.days + (1 if delta.seconds > 0 else 0))
        if serializer.validated_data.get('nights') is None and departure_date and return_date:
            delta = return_date - departure_date
            serializer.validated_data['nights'] = max(0, delta.days)

        if serializer.validated_data.get('stage_id') is None:
            serializer.validated_data['stage_id'] = 1

        calculated_distance = serializer.validated_data.get('calculated_distance')
        user_distance = serializer.validated_data.get('user_distance')
        if calculated_distance is None:
            if auto_distance:
                calculated_distance = self._distance_km(
                    serializer.validated_data.get('origin'),
                    serializer.validated_data.get('destination'),
                )
            if calculated_distance is None and user_distance is not None:
                calculated_distance = user_distance

        if calculated_distance is None:
            raise serializers.ValidationError(
                {"calculated_distance": "Provide calculated_distance, or set auto_distance and valid origin/destination."}
            )

        serializer.validated_data['calculated_distance'] = calculated_distance
        if user_distance is None:
            serializer.validated_data['user_distance'] = calculated_distance

        with transaction.atomic():
            claim = Claim.objects.create(**serializer.validated_data)

            claim_lines = []
            for item in allowances:
                if not isinstance(item, dict):
                    raise serializers.ValidationError({"allowances": "Each allowance must be an object."})
                try:
                    allowance_id_value = item.get('allowance_id', item.get('allowance'))
                    allowance_id = int(allowance_id_value)
                    quantity = float(item.get('quantity'))
                    amount = float(item.get('amount'))
                except (TypeError, ValueError):
                    raise serializers.ValidationError(
                        {"allowances": "Each allowance must include allowance/allowance_id, quantity, amount."}
                    )
                claim_lines.append(
                    ClaimLine(
                        claim_id=claim.id,
                        allowance_id=allowance_id,
                        quantity=quantity,
                        amount=amount,
                    )
                )

            if claim_lines:
                ClaimLine.objects.bulk_create(claim_lines)

        output = self.get_serializer(claim)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=drf_status.HTTP_201_CREATED, headers=headers)


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


class LocationView(viewsets.ReadOnlyModelViewSet):
    serializer_class = LocationSerializer
    queryset = Location.objects.all().order_by('name')
