from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=150)
    isbn = models.CharField(
        max_length=13,
        unique=True,
        validators=[RegexValidator(r"^\d{10}(\d{3})?$", "ISBN must be 10 or 13 digits.")],
    )
    category = models.CharField(max_length=80)
    publication_year = models.PositiveSmallIntegerField(validators=[MinValueValidator(1000)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} — {self.author}"

    def clean(self):
        super().clean()
        if self.publication_year and self.publication_year > timezone.now().year:
            raise ValidationError({"publication_year": "Publication year cannot be in the future."})


class BorrowRecord(models.Model):
    class Status(models.TextChoices):
        BORROWED = "borrowed", "Borrowed"
        RETURNED = "returned", "Returned"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="borrow_records")
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="borrow_records"
    )
    borrow_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateTimeField()
    return_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BORROWED)

    class Meta:
        ordering = ["-borrow_date"]
        indexes = [models.Index(fields=["book", "status"]), models.Index(fields=["member", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["book"],
                condition=Q(status="borrowed"),
                name="unique_active_loan_per_book",
            ),
            models.CheckConstraint(
                condition=Q(due_date__gt=F("borrow_date")),
                name="borrow_due_date_after_borrow_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="borrowed", return_date__isnull=True)
                    | Q(status="returned", return_date__isnull=False)
                ),
                name="borrow_status_matches_return_date",
            ),
        ]

    def __str__(self):
        return f"{self.book.title} → {self.member} ({self.status})"


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    ACTIVE_STATUSES = (Status.PENDING, Status.READY)

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reservations")
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations"
    )
    reservation_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["reservation_date", "id"]
        indexes = [models.Index(fields=["book", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["book", "member"],
                condition=Q(status__in=["pending", "ready"]),
                name="unique_active_reservation_per_member_book",
            ),
        ]

    def __str__(self):
        return f"{self.member} reserved {self.book.title} ({self.status})"

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES
