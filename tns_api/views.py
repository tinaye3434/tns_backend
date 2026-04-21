from django.db import transaction, close_old_connections
import threading
import logging
import os
import csv
import io
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_date, parse_datetime
from django.core.mail import send_mail
from urllib import request as urlrequest
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
import socket
import ssl
import json
import math
from datetime import timedelta
from django.utils import timezone
import numpy as np
from rest_framework import status as drf_status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.models import Token
from .serializers import (
    AllowanceSerializer,
    ApprovalStageSerializer,
    EmployeeSerializer,
    ClaimsSerializer,
    ClaimLineSerializer,
    LocationSerializer,
    UserSerializer,
    ReceiptSerializer,
    GPSValidationSerializer,
    ThresholdConfigSerializer,
)
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
    ApprovalStatus,
    UserRole,
    UserProfile,
    AuditLog,
    Receipt,
    GPSValidation,
    OCRResult,
    ThresholdConfig,
)
from . import fraud
from .ocr import run_ocr

logger = logging.getLogger(__name__)


def _request_actor(request):
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user
    return None


def _create_employee_with_user(
    serializer,
    password: str | None = None,
    role: str = UserRole.EMPLOYEE,
):
    with transaction.atomic():
        employee = serializer.save()

        temp_password = None
        user = getattr(employee, "user", None)
        if employee.user_id is None:
            username = (employee.email or "").strip()
            if not username:
                raise serializers.ValidationError({"email": "Email is required to create a user."})

            user = User.objects.filter(username=username).first()
            if not user and employee.email:
                user = User.objects.filter(email=employee.email).first()

            if user and getattr(user, "employee_profile", None):
                raise serializers.ValidationError(
                    {"email": "A user with this email is already linked to an employee."}
                )

            if not user:
                user = User.objects.create(
                    username=username,
                    email=employee.email,
                    first_name=employee.first_name,
                    last_name=employee.surname,
                    is_active=True,
                )
                chosen_password = password or get_random_string(12)
                if password is None:
                    temp_password = chosen_password
                user.set_password(chosen_password)
                user.save(update_fields=["password"])

            updated_fields = []
            if not user.email and employee.email:
                user.email = employee.email
                updated_fields.append("email")
            if not user.first_name and employee.first_name:
                user.first_name = employee.first_name
                updated_fields.append("first_name")
            if not user.last_name and employee.surname:
                user.last_name = employee.surname
                updated_fields.append("last_name")
            if updated_fields:
                user.save(update_fields=updated_fields)

            employee.user = user
            employee.save(update_fields=["user"])

        profile, _ = UserProfile.objects.get_or_create(user=user or employee.user)
        profile.role = role
        profile.save(update_fields=["role"])

    return employee, (user or employee.user), temp_password


def _build_ocr_result(receipt, claim_line, claim, ocr_payload):
    match_status = "processed"
    notes = []
    total_amount = ocr_payload.get("total_amount")
    receipt_date = ocr_payload.get("receipt_date")

    OCRResult.objects.create(
        receipt=receipt,
        vendor_name=ocr_payload.get("vendor_name", ""),
        receipt_date=receipt_date,
        total_amount=total_amount,
        tax_amount=ocr_payload.get("tax_amount"),
        receipt_number=ocr_payload.get("receipt_number", ""),
        match_status=match_status,
        notes=" ".join(notes).strip(),
        raw_text=ocr_payload.get("raw_text", ""),
    )


def _process_receipt_ids(receipt_ids, force=False):
    close_old_connections()
    try:
        for receipt in Receipt.objects.filter(id__in=receipt_ids):
            if OCRResult.objects.filter(receipt=receipt).exists():
                if not force:
                    continue
                OCRResult.objects.filter(receipt=receipt).delete()
            claim_line = receipt.claim_line
            claim = Claim.objects.filter(id=claim_line.claim_id).first()
            try:
                ocr_payload = run_ocr(receipt.file.path)
            except Exception:
                logger.exception("OCR failed for receipt %s", receipt.id)
                OCRResult.objects.create(
                    receipt=receipt,
                    vendor_name="",
                    receipt_number="",
                    match_status="error",
                    notes="OCR processing failed.",
                    raw_text="",
                )
                continue

            _build_ocr_result(receipt, claim_line, claim, ocr_payload)
    finally:
        close_old_connections()


def _queue_receipt_processing(receipt_ids, force=False):
    if not receipt_ids:
        return False
    thread = threading.Thread(
        target=_process_receipt_ids,
        args=(receipt_ids, force),
        daemon=True,
    )
    thread.start()
    return True

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

    @action(detail=True, methods=['put'], url_path='employees')
    def employees(self, request, pk=None):
        stage = self.get_object()
        ids = request.data.get('ids')

        if not isinstance(ids, list):
            return Response(
                {"detail": "ids must be a list of employee IDs"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        try:
            employee_ids = [int(emp_id) for emp_id in ids]
        except (TypeError, ValueError):
            return Response(
                {"detail": "ids must contain only integers"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        employees = list(Employee.objects.filter(id__in=employee_ids))
        if len(employees) != len(set(employee_ids)):
            return Response(
                {"detail": "One or more employee IDs are invalid"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            current_ids = set(stage.employees.values_list('id', flat=True))
            new_ids = set(employee_ids)
            added_ids = new_ids - current_ids
            removed_ids = current_ids - new_ids

            stage.employees.set(employees)

            if added_ids:
                for employee in Employee.objects.filter(id__in=added_ids):
                    if not employee.user:
                        continue
                    profile, _ = UserProfile.objects.get_or_create(user=employee.user)
                    if profile.role not in {UserRole.ADMIN, UserRole.SUPERUSER}:
                        profile.role = UserRole.APPROVER
                        profile.save(update_fields=["role"])

            if removed_ids:
                for employee in Employee.objects.filter(id__in=removed_ids):
                    if not employee.user:
                        continue
                    profile, _ = UserProfile.objects.get_or_create(user=employee.user)
                    if profile.role in {UserRole.ADMIN, UserRole.SUPERUSER}:
                        continue
                    remaining = employee.approval_stages.exclude(id=stage.id).exists()
                    if not remaining:
                        profile.role = UserRole.EMPLOYEE
                        profile.save(update_fields=["role"])

        serializer = self.get_serializer(stage)
        return Response(serializer.data)


class EmployeeView(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    queryset = Employee.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        employee, user, temp_password = _create_employee_with_user(serializer)

        output = self.get_serializer(employee).data
        if temp_password:
            output["temporary_password"] = temp_password
            try:
                if employee.email:
                    send_mail(
                        "Your Travel Claims Account",
                        f"Hello {employee.first_name},\n\nYour account has been created.\nUsername: {user.username}\nTemporary password: {temp_password}\n\nPlease log in and change your password.",
                        None,
                        [employee.email],
                        fail_silently=True,
                    )
            except Exception:
                pass
        headers = self.get_success_headers(output)
        return Response(output, status=drf_status.HTTP_201_CREATED, headers=headers)


class ClaimView(viewsets.ModelViewSet):
    serializer_class = ClaimsSerializer
    queryset = Claim.objects.all()

    def _distance_km(self, origin_name, destination_name):
        if not origin_name or not destination_name:
            return None
        origin = Location.objects.filter(name__iexact=origin_name).first()
        destination = Location.objects.filter(name__iexact=destination_name).first()
        if not origin or not destination:
            origin_coords = self._geocode_location(origin_name)
            destination_coords = self._geocode_location(destination_name)
            if not origin_coords or not destination_coords:
                return None
            return self._haversine_km(origin_coords, destination_coords)

        # Haversine formula
        return self._haversine_km(
            (origin.latitude, origin.longitude),
            (destination.latitude, destination.longitude),
        )

    def _haversine_km(self, origin_coords, destination_coords):
        radius_km = 6371.0
        lat1, lon1 = origin_coords
        lat2, lon2 = destination_coords
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c

    def _geocode_location(self, query):
        params = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
            "countrycodes": "zw",
        }
        email = os.getenv("NOMINATIM_EMAIL", "")
        if email:
            params["email"] = email

        url = f"https://nominatim.openstreetmap.org/search?{urlencode(params)}"
        req = urlrequest.Request(
            url,
            headers={
                "User-Agent": "tns-backend/1.0 (contact: support@example.com)",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if not payload:
                return None
            item = payload[0]
            return float(item["lat"]), float(item["lon"])
        except Exception:
            return None

    def _get_threshold_pct(self):
        record = ThresholdConfig.objects.filter(key="GPS_VARIANCE_THRESHOLD").first()
        if record:
            return float(record.value)
        return float(os.getenv("GPS_VARIANCE_THRESHOLD", "0.15"))

    def _update_gps_validation(self, claim, claimed_distance):
        if claimed_distance is None:
            return

        threshold_pct = self._get_threshold_pct()
        validation = GPSValidation.objects.filter(claim=claim).first()
        system_distance = None

        if validation:
            system_distance = validation.adjusted_distance_km
        if system_distance is None:
            system_distance = claim.user_distance

        if not system_distance:
            return

        variance_km = claimed_distance - system_distance
        variance_pct = abs(variance_km) / max(system_distance, 1)
        status = "valid" if variance_pct <= threshold_pct else "flagged"

        if validation:
            validation.claimed_distance_km = claimed_distance
            validation.variance_km = variance_km
            validation.variance_pct = variance_pct
            validation.threshold_pct = threshold_pct
            validation.status = status
            validation.save(
                update_fields=[
                    "claimed_distance_km",
                    "variance_km",
                    "variance_pct",
                    "threshold_pct",
                    "status",
                ]
            )

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

        if serializer.validated_data.get('employee_id') is None:
            authenticated_user = getattr(request, "user", None)
            if authenticated_user and authenticated_user.is_authenticated:
                employee = Employee.objects.filter(user=authenticated_user).first()
                if employee:
                    serializer.validated_data['employee_id'] = employee.id

        employee_id = serializer.validated_data.get('employee_id')
        if employee_id is None:
            raise serializers.ValidationError(
                {"detail": "Unable to determine the employee for this claim."}
            )

        if employee_id is not None:
            pending_claim = (
                Claim.objects.filter(
                    employee_id=employee_id,
                    approval_status=ApprovalStatus.PENDING,
                    documents_submitted=False,
                )
                .order_by("-id")
                .first()
            )
            if pending_claim:
                raise serializers.ValidationError(
                    {
                        "detail": (
                            "Please submit receipts for your previous claim "
                            f"(ID {pending_claim.id}) before creating a new one."
                        )
                    }
                )

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

        calculated_distance = self._distance_km(
            serializer.validated_data.get('origin'),
            serializer.validated_data.get('destination'),
        )

        if calculated_distance is None:
            raise serializers.ValidationError(
                {"calculated_distance": "Unable to calculate distance for the given locations."}
            )

        errands_factor = 1.2
        adjusted_distance = calculated_distance * errands_factor

        serializer.validated_data['calculated_distance'] = calculated_distance
        serializer.validated_data['user_distance'] = adjusted_distance

        with transaction.atomic():
            claim = Claim.objects.create(**serializer.validated_data)

            GPSValidation.objects.create(
                claim=claim,
                origin=serializer.validated_data.get('origin', ''),
                destination=serializer.validated_data.get('destination', ''),
                base_distance_km=calculated_distance,
                adjusted_distance_km=adjusted_distance,
                threshold_pct=self._get_threshold_pct(),
                errands_factor=errands_factor,
                source="nominatim",
            )

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

        snapshot = fraud.get_latest_model_snapshot()
        if snapshot:
            results = fraud.score_claims([claim], snapshot)
            if results and results[0].get("auto_approve"):
                final_stage = ApprovalStage.objects.order_by("-order", "-id").first()
                if final_stage:
                    claim.stage_id = final_stage.id
                    claim.approval_status = ApprovalStatus.APPROVED
                    claim.save(update_fields=["stage_id", "approval_status"])
                    AuditLog.objects.create(
                        actor=request.user if getattr(request.user, "is_authenticated", False) else None,
                        action="auto_approved_low_risk",
                        target_user=None,
                        metadata={
                            "claim_id": claim.id,
                            "risk_score": results[0].get("score"),
                            "model_snapshot_id": results[0].get("model_snapshot_id"),
                            "rule_flags": results[0].get("rule_flags", []),
                        },
                    )

        output = self.get_serializer(claim)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=drf_status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        claim = serializer.save()

        claimed_distance = serializer.validated_data.get('actual_mileage')
        if claimed_distance is not None:
            self._update_gps_validation(claim, claimed_distance)

        return Response(self.get_serializer(claim).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='decision')
    def decision(self, request, pk=None):
        claim = self.get_object()
        actor = _request_actor(request)

        if claim.approval_status != ApprovalStatus.PENDING:
            return Response(
                {"detail": "Only pending claims can be actioned."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        decision = (request.data.get("decision") or "").strip().lower()
        justification = (request.data.get("justification") or "").strip()
        if decision not in {"approve", "deny", "reject"}:
            return Response(
                {"detail": "decision must be either 'approve' or 'deny'."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        if not justification:
            return Response(
                {"detail": "A justification is required."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        if decision == "approve":
            current_stage = ApprovalStage.objects.filter(id=claim.stage_id).first()
            next_stage = None
            if current_stage:
                next_stage = (
                    ApprovalStage.objects.filter(order__gt=current_stage.order)
                    .order_by("order", "id")
                    .first()
                )
            else:
                next_stage = ApprovalStage.objects.order_by("order", "id").first()

            if next_stage:
                claim.stage_id = next_stage.id
                claim.save(update_fields=["stage_id"])
                detail = f"Claim approved and moved to stage {next_stage.id}."
            else:
                claim.approval_status = ApprovalStatus.APPROVED
                claim.save(update_fields=["approval_status"])
                detail = "Claim approved."

            audit_action = "claim_approved"
        else:
            claim.approval_status = ApprovalStatus.REJECTED
            claim.save(update_fields=["approval_status"])
            detail = "Claim rejected."
            audit_action = "claim_rejected"

        AuditLog.objects.create(
            actor=actor,
            action=audit_action,
            target_user=None,
            metadata={
                "claim_id": claim.id,
                "decision": "approve" if decision == "approve" else "deny",
                "justification": justification,
                "stage_id": claim.stage_id,
                "approval_status": claim.approval_status,
            },
        )

        serializer = self.get_serializer(claim)
        return Response(
            {
                "detail": detail,
                "claim": serializer.data,
            },
            status=drf_status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='submit-documents')
    def submit_documents(self, request, pk=None):
        claim = self.get_object()
        receipts_qs = Receipt.objects.filter(claim_line__claim_id=claim.id)
        pending_ids = list(
            Receipt.objects.filter(
                claim_line__claim_id=claim.id,
                ocr_result__isnull=True,
            ).values_list("id", flat=True)
        )

        started = _queue_receipt_processing(pending_ids)
        if receipts_qs.exists() and not claim.documents_submitted:
            claim.documents_submitted = True
            claim.save(update_fields=["documents_submitted"])
        if not started:
            return Response(
                {"detail": "No pending receipts to process."},
                status=drf_status.HTTP_200_OK,
            )

        return Response(
            {"detail": "Document processing started in the background."},
            status=drf_status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=['post'], url_path='reprocess-ocr')
    def reprocess_ocr(self, request, pk=None):
        claim = self.get_object()
        receipts_qs = Receipt.objects.filter(claim_line__claim_id=claim.id)
        receipt_ids = list(receipts_qs.values_list("id", flat=True))

        started = _queue_receipt_processing(receipt_ids, force=True)
        if receipts_qs.exists() and not claim.documents_submitted:
            claim.documents_submitted = True
            claim.save(update_fields=["documents_submitted"])
        if not started:
            return Response(
                {"detail": "No receipts to process."},
                status=drf_status.HTTP_200_OK,
            )

        return Response(
            {"detail": "OCR reprocessing started in the background."},
            status=drf_status.HTTP_202_ACCEPTED,
        )
    @action(detail=True, methods=['get'], url_path='documents-summary')
    def documents_summary(self, request, pk=None):
        claim = self.get_object()
        receipts = (
            Receipt.objects.filter(claim_line__claim_id=claim.id)
            .select_related("ocr_result", "claim_line")
        )

        total = receipts.count()
        processed = 0
        pending = 0
        valid = 0
        mismatch = 0
        error = 0
        other = 0

        for receipt in receipts:
            if hasattr(receipt, "ocr_result"):
                processed += 1
                status = (receipt.ocr_result.match_status or "").lower()
                if status == "valid":
                    valid += 1
                elif status == "mismatch":
                    mismatch += 1
                elif status == "error":
                    error += 1
                elif status == "pending":
                    pending += 1
                else:
                    other += 1
            else:
                pending += 1

        serializer = ReceiptSerializer(receipts, many=True)
        return Response(
            {
                "claim_id": claim.id,
                "documents_submitted": claim.documents_submitted,
                "total_receipts": total,
                "processed_receipts": processed,
                "pending_receipts": pending,
                "valid_receipts": valid,
                "mismatch_receipts": mismatch,
                "error_receipts": error,
                "other_receipts": other,
                "receipts": serializer.data,
            },
            status=drf_status.HTTP_200_OK,
        )

    @action(detail=True, methods=['get'], url_path='risk-score')
    def risk_score(self, request, pk=None):
        claim = self.get_object()
        snapshot = fraud.get_latest_model_snapshot()
        if not snapshot:
            return Response(
                {"detail": "Fraud model has not been trained yet."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        results = fraud.score_claims([claim], snapshot)
        if not results:
            return Response(
                {"detail": "Unable to compute risk score for this claim."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        return Response(results[0], status=drf_status.HTTP_200_OK)


class ClaimLineView(viewsets.ModelViewSet):
    serializer_class = ClaimLineSerializer
    queryset = ClaimLine.objects.all()

    @action(detail=True, methods=['get', 'post'], url_path='receipts')
    def receipts(self, request, pk=None):
        claim_line = self.get_object()

        if request.method.lower() == 'get':
            receipts = Receipt.objects.filter(claim_line=claim_line)
            serializer = ReceiptSerializer(receipts, many=True)
            return Response(serializer.data)

        files = request.FILES.getlist('files')
        if not files:
            return Response(
                {"detail": "No files uploaded. Use multipart form-data with files."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        invalid = [f.name for f in files if not (getattr(f, "content_type", "") or "").startswith("image/")]
        if invalid:
            return Response(
                {"detail": f"Only image uploads are supported. Invalid files: {', '.join(invalid)}"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        created = []
        for uploaded in files:
            receipt = Receipt.objects.create(
                claim_line=claim_line,
                file=uploaded,
                file_name=uploaded.name,
                file_type=getattr(uploaded, "content_type", "") or "",
            )
            created.append(receipt)

        serializer = ReceiptSerializer(created, many=True)
        return Response(serializer.data, status=drf_status.HTTP_201_CREATED)


class ReceiptView(viewsets.ModelViewSet):
    serializer_class = ReceiptSerializer
    queryset = Receipt.objects.all()


class GPSValidationView(viewsets.ReadOnlyModelViewSet):
    serializer_class = GPSValidationSerializer
    queryset = GPSValidation.objects.all()


class ThresholdConfigView(viewsets.ModelViewSet):
    serializer_class = ThresholdConfigSerializer
    queryset = ThresholdConfig.objects.all()


@api_view(['POST'])
# @permission_classes([IsAuthenticated, IsAdminRole])
def train_fraud_model_view(request):
    trained_from = request.data.get("from_date") or request.data.get("from_datetime")
    trained_to = request.data.get("to_date") or request.data.get("to_datetime")

    def _parse(value):
        if not value:
            return None
        dt = parse_datetime(value)
        if dt:
            return dt
        d = parse_date(value)
        if d:
            return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))
        return None

    from_dt = _parse(trained_from)
    to_dt = _parse(trained_to)

    try:
        snapshot = fraud.train_fraud_model(trained_from=from_dt, trained_to=to_dt)
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "detail": "Fraud model trained.",
            "snapshot_id": snapshot.id,
            "training_rows": snapshot.training_rows,
            "training_quality": fraud.training_quality(snapshot.training_rows)["quality"],
            "trained_from": snapshot.trained_from,
            "trained_to": snapshot.trained_to,
        },
        status=drf_status.HTTP_201_CREATED,
    )


@api_view(['POST'])
# @permission_classes([IsAuthenticated, IsAdminRole])
def train_fraud_model_csv_view(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"detail": "Upload a CSV file using form-data field 'file'."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    try:
        raw = uploaded.read().decode("utf-8-sig")
    except Exception:
        return Response(
            {"detail": "Unable to read CSV file. Ensure it is UTF-8 encoded."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return Response(
            {"detail": "CSV must include a header row."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    feature_columns = fraud.FEATURE_COLUMNS
    missing = [col for col in feature_columns if col not in reader.fieldnames]
    if missing:
        return Response(
            {"detail": f"CSV missing required columns: {', '.join(missing)}"},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    rows = []
    for idx, row in enumerate(reader, start=2):
        values = []
        for col in feature_columns:
            raw_value = (row.get(col) or "").strip()
            if raw_value == "":
                values.append(0.0)
                continue
            try:
                values.append(float(raw_value))
            except ValueError:
                return Response(
                    {"detail": f"Invalid numeric value at row {idx}, column '{col}'."},
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )
        rows.append(values)

    if not rows:
        return Response(
            {"detail": "CSV contains no data rows."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    trained_from = request.data.get("from_date") or request.data.get("from_datetime")
    trained_to = request.data.get("to_date") or request.data.get("to_datetime")

    def _parse(value):
        if not value:
            return None
        dt = parse_datetime(value)
        if dt:
            return dt
        d = parse_date(value)
        if d:
            return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))
        return None

    from_dt = _parse(trained_from)
    to_dt = _parse(trained_to)

    try:
        snapshot = fraud.train_fraud_model_from_matrix(
            np.array(rows, dtype=float),
            feature_columns,
            trained_from=from_dt,
            trained_to=to_dt,
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "detail": "Fraud model trained from CSV.",
            "snapshot_id": snapshot.id,
            "training_rows": snapshot.training_rows,
            "training_quality": fraud.training_quality(snapshot.training_rows)["quality"],
            "trained_from": snapshot.trained_from,
            "trained_to": snapshot.trained_to,
        },
        status=drf_status.HTTP_201_CREATED,
    )


@api_view(['GET'])
# @permission_classes([IsAuthenticated, IsAdminRole])
def fraud_model_status_view(request):
    snapshot = fraud.get_latest_model_snapshot()
    payload = fraud.model_status(snapshot)
    if snapshot:
        payload["training_quality"] = fraud.training_quality(snapshot.training_rows)["quality"]
    return Response(payload, status=drf_status.HTTP_200_OK)


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
            "approval_status": _choice_list(ApprovalStatus),
            "user_role": _choice_list(UserRole),
        }
    )


@api_view(['GET'])
def openai_health_view(request):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return Response(
            {"configured": False, "status": "missing_key", "detail": "OPENAI_API_KEY not set."},
            status=drf_status.HTTP_200_OK,
        )

    req = urlrequest.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            return Response(
                {"configured": True, "status": "ok", "detail": f"HTTP {resp.status}"},
                status=drf_status.HTTP_200_OK,
            )
    except HTTPError as error:
        status = "unauthorized" if error.code == 401 else "error"
        return Response(
            {
                "configured": True,
                "status": status,
                "detail": f"HTTP {error.code}: {error.reason}",
            },
            status=drf_status.HTTP_200_OK,
        )
    except (socket.timeout, TimeoutError):
        return Response(
            {"configured": True, "status": "timeout", "detail": "Request timed out."},
            status=drf_status.HTTP_200_OK,
        )
    except ssl.SSLError as error:
        return Response(
            {"configured": True, "status": "ssl_error", "detail": f"SSL error: {error}"},
            status=drf_status.HTTP_200_OK,
        )
    except URLError as error:
        reason = error.reason
        reason_text = str(reason) if reason else "Unknown network error."
        return Response(
            {"configured": True, "status": "network_error", "detail": reason_text},
            status=drf_status.HTTP_200_OK,
        )
    except Exception as error:
        logger.exception("OpenAI health check failed.")
        return Response(
            {
                "configured": True,
                "status": "error",
                "detail": f"{error.__class__.__name__}: {error}",
            },
            status=drf_status.HTTP_200_OK,
        )


class LocationView(viewsets.ReadOnlyModelViewSet):
    serializer_class = LocationSerializer
    queryset = Location.objects.all().order_by('name')


@api_view(['POST'])
# @permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response(
            {"detail": "username and password are required."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if not user:
        return Response(
            {"detail": "Invalid credentials."},
            status=drf_status.HTTP_401_UNAUTHORIZED,
        )

    token, _ = Token.objects.get_or_create(user=user)
    profile, _ = UserProfile.objects.get_or_create(user=user)

    return Response(
        {
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": profile.role,
            },
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def signup_view(request):
    password = request.data.get("password")
    confirm_password = request.data.get("confirm_password")

    if not password or len(str(password)) < 8:
        return Response(
            {"detail": "Password must be at least 8 characters long."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    if password != confirm_password:
        return Response(
            {"detail": "Password confirmation does not match."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    payload = request.data.copy()
    payload.setdefault("status", Status.ACTIVE)
    serializer = EmployeeSerializer(data=payload)
    serializer.is_valid(raise_exception=True)

    try:
        employee, user, _temp_password = _create_employee_with_user(serializer, password=str(password))
    except serializers.ValidationError as exc:
        raise exc

    token, _ = Token.objects.get_or_create(user=user)
    profile, _ = UserProfile.objects.get_or_create(user=user)

    return Response(
        {
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": profile.role,
            },
            "employee": EmployeeSerializer(employee).data,
        },
        status=drf_status.HTTP_201_CREATED,
    )


@api_view(['POST'])
# @permission_classes([IsAuthenticated])
def logout_view(request):
    actor = _request_actor(request)
    if actor:
        Token.objects.filter(user=actor).delete()
    return Response({"detail": "Logged out."})


@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def me_view(request):
    actor = _request_actor(request)
    if not actor:
        return Response(
            {
                "id": None,
                "username": "",
                "email": "",
                "first_name": "",
                "last_name": "",
                "is_active": False,
                "role": UserRole.EMPLOYEE,
            }
        )

    serializer = UserSerializer(actor)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def users_view(request):
    users = User.objects.all().order_by('username')
    serializer = UserSerializer(users, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
def user_role_update_view(request, user_id):
    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "User not found."},
            status=drf_status.HTTP_404_NOT_FOUND,
        )

    role = (request.data.get("role") or "").strip().upper()
    valid_roles = {choice for choice, _label in UserRole.choices}
    if role not in valid_roles:
        return Response(
            {"detail": f"Invalid role. Allowed roles: {', '.join(sorted(valid_roles))}."},
            status=drf_status.HTTP_400_BAD_REQUEST,
        )

    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    previous_role = profile.role
    if previous_role != role:
        profile.role = role
        profile.save(update_fields=["role"])
        AuditLog.objects.create(
            actor=_request_actor(request),
            action="role_updated",
            target_user=target_user,
            metadata={
                "previous_role": previous_role,
                "new_role": role,
            },
        )

    serializer = UserSerializer(target_user)
    return Response(serializer.data, status=drf_status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_view(request):
    user_id = request.data.get('user_id')
    username = request.data.get('username')
    email = request.data.get('email')

    user = None
    if user_id:
        user = User.objects.filter(id=user_id).first()
    if not user and username:
        user = User.objects.filter(username=username).first()
    if not user and email:
        user = User.objects.filter(email=email).first()

    if not user:
        return Response(
            {"detail": "User not found."},
            status=drf_status.HTTP_404_NOT_FOUND,
        )

    temp_password = get_random_string(12)
    user.set_password(temp_password)
    user.save(update_fields=["password"])

    AuditLog.objects.create(
        actor=_request_actor(request),
        action="password_reset",
        target_user=user,
        metadata={"method": "temporary_password"},
    )

    return Response(
        {
            "detail": "Password reset. Share the temporary password with the user.",
            "temporary_password": temp_password,
        }
    )

