from django.db import models
from django.db.models import Max
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

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
    FOUR = 4, "Four"
    FIVE = 5, "Five"
    SIX = 6, "Six"
    SEVEN = 7, "Seven"
    EIGHT = 8, "Eight"
    NINE = 9, "Nine"
    TEN = 10, "Ten"
    ELEVEN = 11, "Eleven"
    TWELVE = 12, "Twelve"


class GradeRange(models.TextChoices):
    LOWER = "LOWER", "Lower"
    MIDDLE = "MIDDLE", "Middle"
    UPPER = "UPPER", "Upper"

    @classmethod
    def from_grade(cls, grade):
        grade_value = int(grade)
        if 1 <= grade_value <= 4:
            return cls.LOWER
        if 5 <= grade_value <= 8:
            return cls.MIDDLE
        if 9 <= grade_value <= 12:
            return cls.UPPER
        raise ValueError("Grade must be between 1 and 12.")


class AllowanceNature(models.TextChoices):
    OUT_OF_STATION = "OUT_OF_STATION", "Out of Station"
    FUEL = "FUEL", "Fuel"
    BREAKFAST = "BREAKFAST", "Breakfast"
    LUNCH = "LUNCH", "Lunch"
    DINNER = "DINNER", "Dinner"
    
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

class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"

class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)
    longitude = models.FloatField()
    latitude = models.FloatField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class Employee(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
    )
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
    nature = models.CharField(
        max_length=20,
        choices=AllowanceNature.choices,
        null=True,
        blank=True,
    )
    grade_range = models.CharField(
        max_length=10,
        choices=GradeRange.choices,
        null=True,
        blank=True,
    )
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
    employees = models.ManyToManyField(
        "Employee",
        blank=True,
        related_name="approval_stages",
    )

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
    actual_mileage = models.FloatField(null=True, blank=True)
    total = models.FloatField()
    stage_id = models.IntegerField()
    documents_submitted = models.BooleanField(default=False)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
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


class Receipt(models.Model):
    claim_line = models.ForeignKey(
        ClaimLine,
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    file = models.FileField(upload_to="receipts/")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.file_name


class OCRResult(models.Model):
    receipt = models.OneToOneField(
        Receipt,
        on_delete=models.CASCADE,
        related_name="ocr_result",
    )
    vendor_name = models.CharField(max_length=255, blank=True)
    receipt_date = models.DateField(null=True, blank=True)
    total_amount = models.FloatField(null=True, blank=True)
    tax_amount = models.FloatField(null=True, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True)
    match_status = models.CharField(max_length=20, default="pending")
    notes = models.TextField(blank=True)
    raw_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"OCR {self.receipt_id} ({self.match_status})"


class ThresholdConfig(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.FloatField()
    unit = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key}={self.value}"


class GPSValidation(models.Model):
    claim = models.OneToOneField(
        Claim,
        on_delete=models.CASCADE,
        related_name="gps_validation",
    )
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    base_distance_km = models.FloatField()
    adjusted_distance_km = models.FloatField()
    claimed_distance_km = models.FloatField(null=True, blank=True)
    variance_km = models.FloatField(null=True, blank=True)
    variance_pct = models.FloatField(null=True, blank=True)
    threshold_pct = models.FloatField(default=0.15)
    status = models.CharField(max_length=20, default="pending")
    errands_factor = models.FloatField(default=1.2)
    source = models.CharField(max_length=50, default="nominatim")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.origin} -> {self.destination}"


class UserRole(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "Employee"
    APPROVER = "APPROVER", "Approver"
    ADMIN = "ADMIN", "System Administrator"
    SUPERUSER = "SUPERUSER", "Super User"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.EMPLOYEE)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )
    action = models.CharField(max_length=100)
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_targets",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.target_user.username if self.target_user else "unknown"
        return f"{self.action} -> {target}"


class FraudModelSnapshot(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    model_blob = models.BinaryField()
    feature_columns = models.JSONField(default=list, blank=True)
    feature_means = models.JSONField(default=list, blank=True)
    feature_stds = models.JSONField(default=list, blank=True)
    score_p05 = models.FloatField(default=0.0)
    score_p95 = models.FloatField(default=1.0)
    training_rows = models.IntegerField(default=0)
    trained_from = models.DateTimeField(null=True, blank=True)
    trained_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"FraudModelSnapshot {self.id}"


class FraudScore(models.Model):
    claim = models.OneToOneField(
        Claim,
        on_delete=models.CASCADE,
        related_name="fraud_score",
    )
    model_snapshot = models.ForeignKey(
        FraudModelSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scores",
    )
    score = models.FloatField()
    raw_score = models.FloatField()
    risk_level = models.CharField(max_length=10, default="medium")
    features = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"FraudScore {self.claim_id}: {self.score:.2f}"


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
