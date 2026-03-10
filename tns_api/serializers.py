from rest_framework import serializers
from .models import Allowance, ApprovalStage, Employee, Claim, ClaimLine, Location, Status

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
            'department': {'required': False, 'allow_blank': True},
            'position': {'required': False, 'allow_blank': True},
            'grade': {'required': False, 'allow_blank': True},
            'gender': {'required': False, 'allow_blank': True},
            'status': {'required': False, 'allow_blank': True},
        }

class ClaimsSerializer(StatusDefaultMixin, serializers.ModelSerializer):
    allowances = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True,
    )
    auto_distance = serializers.BooleanField(required=False, default=False, write_only=True)
    employee = serializers.CharField(required=False, write_only=True)
    total_allowances = serializers.FloatField(required=False, write_only=True)

    class Meta:
        model = Claim
        fields = (
            'id',
            'employee_id',
            'employee',
            'purpose',
            'departure_date',
            'return_date',
            'nights',
            'days',
            'origin',
            'destination',
            'user_distance',
            'calculated_distance',
            'total',
            'total_allowances',
            'stage_id',
            'status',
            'allowances',
            'auto_distance',
        )
        extra_kwargs = {
            'status': {'required': False},
            'user_distance': {'required': False},
            'calculated_distance': {'required': False},
            'nights': {'required': False},
            'days': {'required': False},
            'stage_id': {'required': False},
            'total': {'required': False},
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


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ('id', 'name', 'longitude', 'latitude')
