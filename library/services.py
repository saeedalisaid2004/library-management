
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from .exceptions import (
    AlreadyBorrowedByMemberError,
    BookAvailableError,
    BookHasActiveLoanError,
    BookHasHistoryError,
    BookUnavailableError,
    BorrowLimitExceededError,
    DuplicateReservationError,
    NotBorrowedError,
    NotLoanOwnerError,
    ReservationNotFoundError,
    ReservedForAnotherMemberError,
)
from .models import Book, BorrowRecord, Reservation


@dataclass
class BookStatus:
    

    book: Book
    active_loan: BorrowRecord | None = None
    queue: list = field(default_factory=list)
    my_reservation: Reservation | None = None
    my_position: int | None = None
    can_borrow: bool = False
    can_reserve: bool = False
    can_return: bool = False


class LibraryService:
    MAX_ACTIVE_LOANS = 3
    LOAN_DURATION_DAYS = 14

    

    def borrow_book(self, member, book):
        """Create a loan for ``member``. Returns the new BorrowRecord."""
        try:
            with transaction.atomic():
                return self._borrow(member, book)
        except IntegrityError:
            
            raise BookUnavailableError("This book was just borrowed by someone else.") from None

    def return_book(self, member, book):
        with transaction.atomic():
            book = self._lock_book(book)
            record = self._active_loan(book)
            if record is None:
                raise NotBorrowedError("This book is not currently borrowed.")
            if record.member_id != member.pk and not member.is_staff:
                raise NotLoanOwnerError("You can only return books that you borrowed.")

            record.status = BorrowRecord.Status.RETURNED
            record.return_date = timezone.now()
            record.save(update_fields=["status", "return_date"])

            self._promote_next(book)  
            return record

    def reserve_book(self, member, book):
        """Add ``member`` to the waiting list of ``book``. Returns the Reservation."""
        try:
            with transaction.atomic():
                book = self._lock_book(book)
                if self._active_reservation(member, book) is not None:
                    raise DuplicateReservationError("You already have an active reservation for this book.")

                active_loan = self._active_loan(book)
                if active_loan is not None and active_loan.member_id == member.pk:
                    raise AlreadyBorrowedByMemberError("You already have this book.")
                if active_loan is None and not self._ordered_queue(book):
                    raise BookAvailableError("This book is available — you can borrow it directly.")

                return Reservation.objects.create(book=book, member=member)
        except IntegrityError:
            raise DuplicateReservationError("You already have an active reservation for this book.") from None

    def cancel_reservation(self, member, book):
        
        with transaction.atomic():
            book = self._lock_book(book)
            reservation = self._active_reservation(member, book)
            if reservation is None:
                raise ReservationNotFoundError("You have no active reservation for this book.")

            was_ready = reservation.status == Reservation.Status.READY
            reservation.status = Reservation.Status.CANCELLED
            reservation.save(update_fields=["status"])

            if was_ready:
                self._promote_next(book)
            return reservation

    def get_next_reservation(self, book):
        
        queue = self._ordered_queue(book)
        return queue[0] if queue else None

    def get_queue_position(self, member, book):
        
        for position, reservation in enumerate(self._ordered_queue(book), start=1):
            if reservation.member_id == member.pk:
                return position
        return None

    def calculate_overdue_days(self, borrow_record, now=None):
        """Whole days past the due date (0 if on time).

        Active loan   -> compared with ``now``.
        Returned loan -> compared with the actual return date (late returns stay visible).
        """
        end = borrow_record.return_date or now or timezone.now()
        return max(0, (end - borrow_record.due_date).days)

    def get_book_status(self, book, member=None):
        """Everything the detail page needs, computed with two queries."""
        active_loan = self._active_loan(book)
        queue = self._ordered_queue(book)
        status = BookStatus(book=book, active_loan=active_loan, queue=queue)
        if member is None or not member.is_authenticated:
            return status

        status.my_reservation = next((r for r in queue if r.member_id == member.pk), None)
        if status.my_reservation is not None:
            status.my_position = queue.index(status.my_reservation) + 1

        head = queue[0] if queue else None
        holds_book = active_loan is not None and active_loan.member_id == member.pk
        status.can_borrow = active_loan is None and (head is None or head.member_id == member.pk)
        status.can_reserve = (
            status.my_reservation is None and not holds_book and (active_loan is not None or bool(queue))
        )
        status.can_return = active_loan is not None and (holds_book or member.is_staff)
        return status

    def delete_book(self, book):
        
        with transaction.atomic():
            book = self._lock_book(book)
            if self._active_loan(book) is not None:
                raise BookHasActiveLoanError("This book is currently on loan and cannot be deleted.")
            if book.borrow_records.exists():
                raise BookHasHistoryError("This book has borrowing history and cannot be deleted.")
            book.delete()

    def count_active_loans(self, member):
        """Number of books the member currently holds."""
        return BorrowRecord.objects.filter(member=member, status=BorrowRecord.Status.BORROWED).count()

    def member_summary(self, member):
        
        return BorrowRecord.objects.filter(member=member).aggregate(
            total_loans=Count("id"),
            active_loans=Count("id", filter=Q(status=BorrowRecord.Status.BORROWED)),
        )


    def _borrow(self, member, book):
        book = self._lock_book(book)

        active_loan = self._active_loan(book)
        if active_loan is not None:
            if active_loan.member_id == member.pk:
                raise BookUnavailableError("You have already borrowed this book.")
            raise BookUnavailableError("This book is currently borrowed by another member.")

        head = self.get_next_reservation(book)
        if head is not None and head.member_id != member.pk:
            raise ReservedForAnotherMemberError(
                "This book is reserved for another member who is first in the waiting list."
            )

        if self.count_active_loans(member) >= self.MAX_ACTIVE_LOANS:
            raise BorrowLimitExceededError(
                f"You can have at most {self.MAX_ACTIVE_LOANS} borrowed books at the same time."
            )

        now = timezone.now()
        record = BorrowRecord.objects.create(
            book=book,
            member=member,
            borrow_date=now,
            due_date=now + timedelta(days=self.LOAN_DURATION_DAYS),
        )
        if head is not None:  
            head.status = Reservation.Status.FULFILLED
            head.save(update_fields=["status"])
        return record

    def _lock_book(self, book):
        
        return Book.objects.select_for_update().get(pk=book.pk)

    def _active_loan(self, book):
        
        return (
            BorrowRecord.objects.select_related("member")
            .filter(book=book, status=BorrowRecord.Status.BORROWED)
            .first()
        )

    def _active_reservation(self, member, book):
        return Reservation.objects.filter(
            book=book, member=member, status__in=Reservation.ACTIVE_STATUSES
        ).first()

    def _ordered_queue(self, book):
        active = Reservation.objects.filter(book=book, status__in=Reservation.ACTIVE_STATUSES).select_related(
            "member"
        )
        return sorted(active, key=lambda r: (r.reservation_date, r.pk))

    def _promote_next(self, book):
        if self._active_loan(book) is not None:
            return None
        head = self.get_next_reservation(book)
        if head is not None and head.status == Reservation.Status.PENDING:
            head.status = Reservation.Status.READY
            head.save(update_fields=["status"])
        return head

