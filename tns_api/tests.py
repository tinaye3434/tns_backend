from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .serializers import AllowanceSerializer, EmployeeSerializer, LocationSerializer
from .models import Allowance, AllowanceNature, Claim, ClaimLine, Employee, GPSValidation, GradeRange, Location
from .views import ClaimLineView, ClaimView, driving_route_view


class GradeRangeTests(TestCase):
    def test_maps_general_grade_range(self):
        self.assertEqual(GradeRange.from_grade(1), GradeRange.GENERAL)
        self.assertEqual(GradeRange.from_grade(8), GradeRange.GENERAL)

    def test_maps_management_grade_range(self):
        self.assertEqual(GradeRange.from_grade(9), GradeRange.MANAGEMENT)

    def test_maps_hods_and_councilors_grade_range(self):
        self.assertEqual(GradeRange.from_grade(10), GradeRange.HODS_AND_COUNCILORS)

    def test_maps_ceo_and_council_chair_grade_range(self):
        self.assertEqual(GradeRange.from_grade(11), GradeRange.CEO_AND_COUNCIL_CHAIR)

    def test_rejects_out_of_range_grade(self):
        with self.assertRaises(ValueError):
            GradeRange.from_grade(0)

        with self.assertRaises(ValueError):
            GradeRange.from_grade(12)

    def test_employee_serializer_includes_grade_range(self):
        employee = Employee(
            first_name="John",
            surname="Doe",
            email="john@example.com",
            phone_number="123456789",
            department="FINANCE",
            position="AUDITOR",
            grade=6,
            gender="M",
            status=1,
        )

        serializer = EmployeeSerializer(employee)

        self.assertEqual(serializer.data["grade_range"], GradeRange.GENERAL)


class AllowanceNatureTests(TestCase):
    def test_allowance_nature_choices(self):
        self.assertEqual(AllowanceNature.OUT_OF_STATION.label, "Out of Station")
        self.assertEqual(AllowanceNature.FUEL.label, "Fuel")
        self.assertEqual(AllowanceNature.BREAKFAST.label, "Breakfast")
        self.assertEqual(AllowanceNature.LUNCH.label, "Lunch")
        self.assertEqual(AllowanceNature.DINNER.label, "Dinner")

    def test_serializer_maps_blank_nature_to_none(self):
        serializer = AllowanceSerializer(
            data={
                "title": "Fuel allowance",
                "nature": "",
                "cost": 12.5,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["nature"])

    def test_serializer_maps_blank_grade_range_to_none(self):
        serializer = AllowanceSerializer(
            data={
                "title": "Meal allowance",
                "grade_range": "",
                "cost": 7.5,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["grade_range"])


class LocationSerializerTests(TestCase):
    def test_serializer_accepts_city_payload(self):
        serializer = LocationSerializer(
            data={
                "name": "New City",
                "longitude": 31.0522,
                "latitude": -17.8292,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


class ClaimCreateResolutionTests(TestCase):
    def test_create_claim_links_matching_employee_from_authenticated_user(self):
        user = User.objects.create_user(
            username="legacy.employee@example.com",
            email="legacy.employee@example.com",
            password="Password123",
        )
        employee = Employee.objects.create(
            first_name="Legacy",
            surname="Employee",
            email="legacy.employee@example.com",
            phone_number="123456789",
            department="FINANCE",
            position="AUDITOR",
            grade=6,
            gender="M",
            status=1,
        )
        Location.objects.update_or_create(
            name="Harare",
            defaults={"longitude": 31.053, "latitude": -17.825},
        )
        Location.objects.update_or_create(
            name="Bulawayo",
            defaults={"longitude": 28.58, "latitude": -20.15},
        )

        request = APIRequestFactory().post(
            "/api/claims/",
            {
                "purpose": "Conference travel",
                "departure_date": timezone.now().isoformat(),
                "return_date": (timezone.now() + timedelta(days=1)).isoformat(),
                "origin": "Harare",
                "destination": "Bulawayo",
                "total_allowances": 0,
                "allowances": [],
            },
            format="json",
        )
        force_authenticate(request, user=user)

        response = ClaimView.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 201)
        employee.refresh_from_db()
        self.assertEqual(employee.user_id, user.id)
        claim = Claim.objects.get(id=response.data["id"])
        self.assertEqual(claim.employee_id, employee.id)


class ClaimReceiptRequirementTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="receipts@example.com",
            email="receipts@example.com",
            password="Password123",
        )
        self.breakfast_allowance = Allowance.objects.create(
            title="Breakfast",
            nature=AllowanceNature.BREAKFAST,
            cost=10,
            status=1,
        )
        self.fuel_allowance = Allowance.objects.create(
            title="Fuel",
            nature=AllowanceNature.FUEL,
            cost=20,
            status=1,
        )

    def create_claim(self):
        return Claim.objects.create(
            employee_id=1,
            purpose="Trip",
            departure_date=timezone.now(),
            return_date=timezone.now() + timedelta(days=1),
            nights=1,
            days=1,
            origin="Harare",
            destination="Bulawayo",
            user_distance=100,
            calculated_distance=80,
            total=100,
            stage_id=1,
        )

    def test_submit_documents_marks_complete_when_no_receipts_are_required(self):
        claim = self.create_claim()
        ClaimLine.objects.create(
            claim_id=claim.id,
            allowance_id=self.breakfast_allowance.id,
            quantity=1,
            amount=10,
        )

        request = self.factory.post(f"/api/claims/{claim.id}/submit-documents/")
        force_authenticate(request, user=self.user)

        response = ClaimView.as_view({"post": "submit_documents"})(request, pk=claim.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "No receipts are required for this claim.")
        claim.refresh_from_db()
        self.assertTrue(claim.documents_submitted)

    def test_submit_documents_requires_receipts_for_fuel_and_out_of_station(self):
        claim = self.create_claim()
        ClaimLine.objects.create(
            claim_id=claim.id,
            allowance_id=self.fuel_allowance.id,
            quantity=1,
            amount=20,
        )

        request = self.factory.post(f"/api/claims/{claim.id}/submit-documents/")
        force_authenticate(request, user=self.user)

        response = ClaimView.as_view({"post": "submit_documents"})(request, pk=claim.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Submit receipts for all fuel and out of station allowances", response.data["detail"])

    def test_receipt_upload_is_rejected_for_non_receipt_allowance_lines(self):
        claim = self.create_claim()
        claim_line = ClaimLine.objects.create(
            claim_id=claim.id,
            allowance_id=self.breakfast_allowance.id,
            quantity=1,
            amount=10,
        )

        uploaded = SimpleUploadedFile("receipt.png", b"fake-image-data", content_type="image/png")
        request = self.factory.post(
            f"/api/claim-lines/{claim_line.id}/receipts/",
            {"files": [uploaded]},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        response = ClaimLineView.as_view({"post": "receipts"})(request, pk=claim_line.id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Receipts can only be uploaded for fuel and out of station allowances.",
        )


class ClaimDistanceBehaviorTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="distance@example.com",
            email="distance@example.com",
            password="Password123",
        )
        self.employee = Employee.objects.create(
            first_name="Distance",
            surname="Tester",
            email="distance@example.com",
            phone_number="123456789",
            department="FINANCE",
            position="AUDITOR",
            grade=6,
            gender="M",
            status=1,
            user=self.user,
        )
        self.harare, _ = Location.objects.update_or_create(
            name="Harare",
            defaults={"longitude": 31.053, "latitude": -17.825},
        )
        self.bulawayo, _ = Location.objects.update_or_create(
            name="Bulawayo",
            defaults={"longitude": 28.58, "latitude": -20.15},
        )

    def test_create_claim_stores_round_trip_calculated_distance(self):
        request = self.factory.post(
            "/api/claims/",
            {
                "purpose": "Distance validation",
                "departure_date": timezone.now().isoformat(),
                "return_date": (timezone.now() + timedelta(days=1)).isoformat(),
                "origin": "Harare",
                "destination": "Bulawayo",
                "total_allowances": 0,
                "allowances": [],
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = ClaimView.as_view({"post": "create"})(request)

        self.assertEqual(response.status_code, 201)
        claim = Claim.objects.get(id=response.data["id"])
        gps_validation = GPSValidation.objects.get(claim=claim)
        one_way_distance = ClaimView()._haversine_km(
            (self.harare.latitude, self.harare.longitude),
            (self.bulawayo.latitude, self.bulawayo.longitude),
        )

        self.assertAlmostEqual(claim.calculated_distance, one_way_distance * 2, places=5)
        self.assertEqual(claim.user_distance, 0.0)
        self.assertAlmostEqual(
            gps_validation.adjusted_distance_km,
            claim.calculated_distance * 1.2,
            places=5,
        )

    def test_updating_actual_mileage_syncs_user_distance_and_gps_validation(self):
        claim = Claim.objects.create(
            employee_id=self.employee.id,
            purpose="Mileage update",
            departure_date=timezone.now(),
            return_date=timezone.now() + timedelta(days=1),
            nights=1,
            days=1,
            origin="Harare",
            destination="Bulawayo",
            user_distance=0,
            calculated_distance=100,
            actual_mileage=None,
            total=50,
            stage_id=1,
        )
        GPSValidation.objects.create(
            claim=claim,
            origin="Harare",
            destination="Bulawayo",
            base_distance_km=100,
            adjusted_distance_km=120,
            threshold_pct=0.15,
            errands_factor=1.2,
            source="nominatim",
        )

        request = self.factory.patch(
            f"/api/claims/{claim.id}/",
            {"actual_mileage": 145.5},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = ClaimView.as_view({"patch": "partial_update"})(request, pk=claim.id)

        self.assertEqual(response.status_code, 200)
        claim.refresh_from_db()
        gps_validation = GPSValidation.objects.get(claim=claim)
        self.assertEqual(claim.actual_mileage, 145.5)
        self.assertEqual(claim.user_distance, 145.5)
        self.assertEqual(gps_validation.claimed_distance_km, 145.5)

    def test_submit_documents_requires_user_distance_entry(self):
        claim = Claim.objects.create(
            employee_id=self.employee.id,
            purpose="Missing distance",
            departure_date=timezone.now(),
            return_date=timezone.now() + timedelta(days=1),
            nights=1,
            days=1,
            origin="Harare",
            destination="Bulawayo",
            user_distance=0,
            calculated_distance=100,
            actual_mileage=None,
            total=50,
            stage_id=1,
        )

        request = self.factory.post(f"/api/claims/{claim.id}/submit-documents/")
        force_authenticate(request, user=self.user)

        response = ClaimView.as_view({"post": "submit_documents"})(request, pk=claim.id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Enter the user distance before submitting receipts.")


class DrivingRouteViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("tns_api.views.urlrequest.urlopen")
    def test_returns_driving_route_geometry(self, mock_urlopen):
        class MockResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return (
                    b'{"code":"Ok","routes":[{"distance":125000.0,"duration":7200.0,'
                    b'"geometry":{"type":"LineString","coordinates":'
                    b'[[31.053,-17.825],[30.4,-18.3],[28.58,-20.15]]}}]}'
                )

        mock_urlopen.return_value = MockResponse()

        request = self.factory.get(
            "/api/routes/driving/",
            {
                "origin_lat": -17.825,
                "origin_lng": 31.053,
                "destination_lat": -20.15,
                "destination_lng": 28.58,
            },
        )

        response = driving_route_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["distance_km"], 125.0)
        self.assertEqual(response.data["duration_minutes"], 120.0)
        self.assertEqual(
            response.data["coordinates"],
            [[-17.825, 31.053], [-18.3, 30.4], [-20.15, 28.58]],
        )

    def test_rejects_missing_coordinate_params(self):
        request = self.factory.get(
            "/api/routes/driving/",
            {
                "origin_lat": -17.825,
                "origin_lng": 31.053,
            },
        )

        response = driving_route_view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("origin_lat, origin_lng, destination_lat, and destination_lng", response.data["detail"])
