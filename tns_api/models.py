from django.db import models
from django.db.models import Max

class Department(models.TextChoices):
    FINANCE = "FINANCE", "Finance"
    HUMAN_RESOURCES = "HUMAN_RESOURCES", "Human Resources"
    ENGINEERING = "ENGINEERING", "Engineering"
    
class Position(models.TextChoices):
    AUDITOR = "AUDITOR", "Auditor"
    ENGINEER = "ENGINEER", "Engineer"
    DRIVER = "DRIVER", "Driver"
    
class Grade(models.IntegerChoices):
    ONE = 1, "One"
    TWO = 2, "Two"
    THREE = 3, "Three"
    
class Gender(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"
    
class TnsClassifications(models.TextChoices):
    DAY = "DAY", "Day"
    NIGHT = "NIGHT", "Night"
    QUANTITY = "QUANTITY", "Quantity"
    
class Status(models.IntegerChoices):
    ACTIVE = 1, "Active"
    INACTIVE = 0, "Inactive"

class Employee(models.Model):
    first_name = models.TextField()
    surname = models.TextField()
    email = models.EmailField()
    phone_number = models.TextField()
    department = models.CharField(
        max_length=20,
        choices=Department.choices,
        default=Department.FINANCE
    )
    position = models.CharField(
        max_length=20,
        choices=Position.choices,
        default=Position.AUDITOR
    )
    grade = models.CharField(
        max_length=2,
        choices=Grade.choices,
        default=Grade.ONE
    )
    gender = models.CharField(
        max_length=1,
        choices=Gender.choices,
        default=Gender.MALE
    )
    status = models.CharField(
        max_length=1,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    
    def _str_(self):
        return self.title
    
class Allowance(models.Model):
    title = models.CharField(max_length=50)
    cost = models.FloatField()
    status = models.CharField(
        max_length=1,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    
    def _str_(self):
        return self.title
    
class ApprovalStage(models.Model):
    title = models.CharField(max_length=20)
    order = models.PositiveIntegerField(default=1, db_index=True)

    def save(self, *args, **kwargs):
        if self._state.adding:
            max_order = ApprovalStage.objects.aggregate(max_order=Max("order"))["max_order"] or 0
            self.order = max_order + 1
        super().save(*args, **kwargs)
    
    def _str_(self):
        return self.title

class Claim(models.Model):
    employee_id = models.IntegerField()
    purpose = models.TextField()
    departure_date = models.DateTimeField()
    return_date = models.DateTimeField()
    nights = models.IntegerField()
    days = models.IntegerField()
    origin = models.TextField()
    destination = models.TextField()
    user_distance = models.FloatField()
    calculated_distance = models.FloatField()
    total = models.FloatField()
    stage_id = models.IntegerField()
    status = models.CharField(
        max_length=1,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    def _str_(self):
        return str(self.employee_id)

class ClaimLine(models.Model):
    claim_id = models.IntegerField()
    allowance_id = models.IntegerField()
    quantity = models.FloatField()
    amount = models.FloatField()

    def _str_(self):
        return str(self.claim_id)
