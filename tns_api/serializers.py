from rest_framework import serializers
from .models import Allowance, ApprovalStage, Employee, Claim, ClaimLine, Status

class StatusDefaultMixin:
    status = serializers.ChoiceField(
        choices=Status.choices,
        required=False,
        allow_blank=True,
    )

    def validate_status(self, value):
        if value == "":
            return Status.ACTIVE
        return value

    def create(self, validated_data):
        validated_data.setdefault('status', Status.ACTIVE)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get('status', None) == "":
            validated_data['status'] = Status.ACTIVE
        return super().update(instance, validated_data)


class AllowanceSerializer(StatusDefaultMixin, serializers.ModelSerializer):
    class Meta:
        model = Allowance
        fields = ('id', 'title', 'cost', 'status')
        extra_kwargs = {
            'status': {'required': False},
        }
        
class ApprovalStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalStage
        fields = ('id', 'title', 'order')
        
class EmployeeSerializer(StatusDefaultMixin, serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ('id', 'first_name', 'surname', 'email', 'phone_number', 'department', 'position', 'grade', 'gender', 'status')
        extra_kwargs = {
            'status': {'required': False},
        }

class ClaimsSerializer(StatusDefaultMixin, serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = (
            'id',
            'employee_id',
            'purpose',
            'departure_date',
            'arrival_date',
            'nights',
            'days',
            'destination',
            'distance_full',
            'total',
            'stage_id',
            'status',
        )
        extra_kwargs = {
            'status': {'required': False},
        }

class ClaimLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimLine
        fields = (
            'id',
            'claim_id',
            'allowance_id',
            'quantity',
            'amount',
        )
