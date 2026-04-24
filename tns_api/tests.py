from django.test import TestCase

from .serializers import AllowanceSerializer, EmployeeSerializer, LocationSerializer
from .models import AllowanceNature, Employee, GradeRange


class GradeRangeTests(TestCase):
    def test_maps_lower_grade_range(self):
        self.assertEqual(GradeRange.from_grade(1), GradeRange.LOWER)
        self.assertEqual(GradeRange.from_grade(4), GradeRange.LOWER)

    def test_maps_middle_grade_range(self):
        self.assertEqual(GradeRange.from_grade(5), GradeRange.MIDDLE)
        self.assertEqual(GradeRange.from_grade(8), GradeRange.MIDDLE)

    def test_maps_upper_grade_range(self):
        self.assertEqual(GradeRange.from_grade(9), GradeRange.UPPER)
        self.assertEqual(GradeRange.from_grade(12), GradeRange.UPPER)

    def test_rejects_out_of_range_grade(self):
        with self.assertRaises(ValueError):
            GradeRange.from_grade(0)

        with self.assertRaises(ValueError):
            GradeRange.from_grade(13)

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

        self.assertEqual(serializer.data["grade_range"], GradeRange.MIDDLE)


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
