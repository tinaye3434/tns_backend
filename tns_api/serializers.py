from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Allowance,
    ApprovalStage,
    Employee,
    Claim,
    ClaimLine,
    Location,
    Status,
    UserProfile,
    UserRole,
    Receipt,
    GPSValidation,
    OCRResult,
    ThresholdConfig,
)

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
    employee_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        read_only=True,
        source='employees',
    )

    class Meta:
        model = ApprovalStage
        fields = ('id', 'title', 'order', 'employee_ids')
        
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
            'actual_mileage',
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
            'actual_mileage': {'required': False},
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


class ReceiptSerializer(serializers.ModelSerializer):
    ocr_result = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = (
            'id',
            'claim_line',
            'file',
            'file_name',
            'file_type',
            'uploaded_at',
            'ocr_result',
        )

    def get_ocr_result(self, obj):
        if not hasattr(obj, "ocr_result"):
            return None
        ocr = obj.ocr_result
        return {
            "vendor_name": ocr.vendor_name,
            "receipt_date": ocr.receipt_date,
            "total_amount": ocr.total_amount,
            "tax_amount": ocr.tax_amount,
            "receipt_number": ocr.receipt_number,
            "match_status": ocr.match_status,
            "notes": ocr.notes,
        }


class GPSValidationSerializer(serializers.ModelSerializer):
    class Meta:
        model = GPSValidation
        fields = (
            'id',
            'claim',
            'origin',
            'destination',
            'base_distance_km',
            'adjusted_distance_km',
            'claimed_distance_km',
            'variance_km',
            'variance_pct',
            'threshold_pct',
            'status',
            'errands_factor',
            'source',
            'created_at',
        )


class ThresholdConfigSerializer(serializers.ModelSerializer):
    ALLOWED_KEYS = {
        "GPS_VARIANCE_THRESHOLD",
    }

    class Meta:
        model = ThresholdConfig
        fields = (
            'id',
            'key',
            'value',
            'unit',
            'description',
            'updated_at',
        )

    def validate_key(self, value):
        if value not in self.ALLOWED_KEYS:
            raise serializers.ValidationError(
                f"Invalid key. Allowed keys: {', '.join(sorted(self.ALLOWED_KEYS))}."
            )
        return value


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'role')

    def get_role(self, obj):
        profile = getattr(obj, 'profile', None)
        if not profile:
            profile = UserProfile.objects.create(user=obj)
        return profile.role if profile else UserRole.EMPLOYEE


class EmployeeSerializer(StatusDefaultMixin, serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = Employee
        fields = (
            'id',
            'user_id',
            'user',
            'first_name',
            'surname',
            'email',
            'phone_number',
            'department',
            'position',
            'grade',
            'gender',
            'status',
        )
        extra_kwargs = {
            'department': {'required': False, 'allow_blank': True},
            'position': {'required': False, 'allow_blank': True},
            'grade': {'required': False, 'allow_blank': True},
            'gender': {'required': False, 'allow_blank': True},
            'status': {'required': False, 'allow_blank': True},
        }
