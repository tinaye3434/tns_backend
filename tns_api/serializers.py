from rest_framework import serializers
from .models import Allowance, ApprovalStage, Employee, Claim

class AllowanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allowance
        fields = ('id', 'title', 'classification', 'price', 'status')
        
class ApprovalStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalStage
        fields = ('id', 'title', 'order', 'status')
        
class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ('id', 'first_name', 'surname', 'email', 'phone_number', 'department', 'position', 'grade', 'gender', 'status')

class ClaimsSerializer(serializers.ModelSerializer):
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

