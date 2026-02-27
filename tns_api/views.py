from django.shortcuts import render
from rest_framework import viewsets
from .serializers import AllowanceSerializer, ApprovalStageSerializer, EmployeeSerializer, ClaimsSerializer
from .models import Allowance, ApprovalStage, Employee, Claim

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

