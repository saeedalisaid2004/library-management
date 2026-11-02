"""Automated tests.  Run with:  python manage.py test"""
import itertools
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
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
from .services import LibraryService

User = get_user_model()
_isbn_counter = itertools.count(1)


def make_book(**overrides):
    data = {
        "title": "Test Book",
        "author": "Some Author",
        "isbn": f"{next(_isbn_counter):013d}",
        "category": "Testing",
        "publication_year": 2020,
    }
    data.update(overrides)
    return Book.objects.create(**data)


class LibraryTestCase(TestCase):
    

    def setUp(self):
        self.service = LibraryService()
        self.ahmed = User.objects.create_user("ahmed", password="pass12345")
        self.sara = User.objects.create_user("sara", password="pass12345")
        self.omar = User.objects.create_user("omar", password="pass12345")
        self.staff = User.objects.create_user("staff", password="pass12345", is_staff=True)
        self.book = make_book()




class AuthTests(TestCase):
    def test_registration_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "saeed",
                "email": "saeed@gmail.com",
                "password1": "1452004s",
                "password2": "1452004s",
            },
        )
        self.assertRedirects(response, reverse("book_list"))
        self.assertTrue(User.objects.filter(username="saeed").exists())
        self.assertIn("_auth_user_id", self.client.session)  

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("register"),
            {"username": "bad", "email": "b@example.com", "password1": "S3cure-pass-123", "password2": "different"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="bad").exists())

    def test_login_and_logout(self):
        User.objects.create_user("lina", password="pass12345")
        response = self.client.post(reverse("login"), {"username": "lina", "password": "pass12345"})
        self.assertRedirects(response, reverse("book_list"))
        self.assertIn("_auth_user_id", self.client.session)

        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_with_wrong_password_fails(self):
        User.objects.create_user("lina", password="pass12345")
        response = self.client.post(reverse("login"), {"username": "lina", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)



class BookCatalogTests(LibraryTestCase):
    def test_staff_can_create_book(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("book_create"),
            {
                "title": "Clean Code",
                "author": "Robert C. Martin",
                "isbn": "978-0-13-235088-4",  
                "category": "Programming",
                "publication_year": 2008,
            },
        )
        book = Book.objects.get(isbn="9780132350884")
        self.assertRedirects(response, reverse("book_detail", args=[book.pk]))
        self.assertEqual(book.title, "Clean Code")

    def test_regular_member_cannot_create_book(self):
        self.client.force_login(self.ahmed)
        response = self.client.post(reverse("book_create"), {"title": "X"})
        self.assertEqual(response.status_code, 403)

    def test_duplicate_isbn_is_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("book_create"),
            {"title": "Dup", "author": "A", "isbn": self.book.isbn, "category": "C", "publication_year": 2000},
        )
        self.assertEqual(response.status_code, 200)  
        self.assertEqual(Book.objects.filter(isbn=self.book.isbn).count(), 1)

    def test_future_publication_year_is_rejected(self):
        self.client.force_login(self.staff)
        future = timezone.now().year + 5
        self.client.post(
            reverse("book_create"),
            {"title": "Future", "author": "A", "isbn": "1234567890", "category": "C", "publication_year": future},
        )
        self.assertFalse(Book.objects.filter(isbn="1234567890").exists())

    def test_search_by_title_or_author_and_filter_by_category(self):
        make_book(title="Python Tricks", author="Dan Bader", category="Programming")
        make_book(title="Cosmos", author="Carl Sagan", category="Science")

        by_title = self.client.get(reverse("book_list"), {"q": "python"})
        self.assertEqual([b.title for b in by_title.context["books"]], ["Python Tricks"])

        by_author = self.client.get(reverse("book_list"), {"q": "sagan"})
        self.assertEqual([b.title for b in by_author.context["books"]], ["Cosmos"])

        by_category = self.client.get(reverse("book_list"), {"category": "Science"})
        self.assertEqual([b.title for b in by_category.context["books"]], ["Cosmos"])

    def test_staff_cannot_delete_book_with_active_loan(self):
        self.service.borrow_book(self.ahmed, self.book)
        with self.assertRaises(BookHasActiveLoanError):
            self.service.delete_book(self.book)

        self.client.force_login(self.staff)
        response = self.client.post(reverse("book_delete", args=[self.book.pk]), follow=True)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())
        self.assertContains(response, "currently on loan")

    def test_book_with_history_cannot_be_deleted_but_clean_book_can(self):
        self.service.borrow_book(self.ahmed, self.book)
        self.service.return_book(self.ahmed, self.book)
        with self.assertRaises(BookHasHistoryError):
            self.service.delete_book(self.book)

        fresh = make_book()
        self.service.delete_book(fresh)
        self.assertFalse(Book.objects.filter(pk=fresh.pk).exists())

class BorrowingTests(LibraryTestCase):
    def test_successful_borrow(self):
        record = self.service.borrow_book(self.ahmed, self.book)
        self.assertEqual(record.status, BorrowRecord.Status.BORROWED)
        self.assertEqual(record.member, self.ahmed)
        self.assertIsNone(record.return_date)
        self.assertEqual((record.due_date - record.borrow_date).days, 14)

    def test_borrow_unavailable_book(self):
        self.service.borrow_book(self.ahmed, self.book)
        with self.assertRaises(BookUnavailableError):
            self.service.borrow_book(self.sara, self.book)
        self.assertEqual(BorrowRecord.objects.filter(book=self.book).count(), 1)

    def test_member_cannot_borrow_same_book_twice(self):
        self.service.borrow_book(self.ahmed, self.book)
        with self.assertRaises(BookUnavailableError):
            self.service.borrow_book(self.ahmed, self.book)

    def test_cannot_exceed_three_active_loans(self):
        books = [make_book() for _ in range(4)]
        for b in books[:3]:
            self.service.borrow_book(self.ahmed, b)
        with self.assertRaises(BorrowLimitExceededError):
            self.service.borrow_book(self.ahmed, books[3])
        self.assertEqual(self.service.count_active_loans(self.ahmed), 3)

    def test_returning_a_book_frees_a_slot_in_the_limit(self):
        books = [make_book() for _ in range(4)]
        for b in books[:3]:
            self.service.borrow_book(self.ahmed, b)
        self.service.return_book(self.ahmed, books[0])
        self.service.borrow_book(self.ahmed, books[3])  
        self.assertEqual(self.service.count_active_loans(self.ahmed), 3)

    def test_borrow_view_requires_login(self):
        response = self.client.post(reverse("borrow_book", args=[self.book.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertEqual(BorrowRecord.objects.count(), 0)

    def test_borrow_view_shows_success_and_error_messages(self):
        self.client.force_login(self.ahmed)
        url = reverse("borrow_book", args=[self.book.pk])
        ok = self.client.post(url, follow=True)
        self.assertContains(ok, "You borrowed")

        self.client.force_login(self.sara)
        failed = self.client.post(url, follow=True)
        self.assertContains(failed, "borrowed by another member")

    def test_borrow_view_rejects_get(self):
        self.client.force_login(self.ahmed)
        response = self.client.get(reverse("borrow_book", args=[self.book.pk]))
        self.assertEqual(response.status_code, 405)

class ReturningTests(LibraryTestCase):
    def test_borrower_can_return(self):
        self.service.borrow_book(self.ahmed, self.book)
        record = self.service.return_book(self.ahmed, self.book)
        self.assertEqual(record.status, BorrowRecord.Status.RETURNED)
        self.assertIsNotNone(record.return_date)
        self.service.borrow_book(self.sara, self.book)  

    def test_other_member_cannot_return(self):
        self.service.borrow_book(self.ahmed, self.book)
        with self.assertRaises(NotLoanOwnerError):
            self.service.return_book(self.sara, self.book)
        self.assertEqual(self.service.count_active_loans(self.ahmed), 1)

    def test_staff_can_return_for_a_member(self):
        self.service.borrow_book(self.ahmed, self.book)
        self.service.return_book(self.staff, self.book)
        self.assertEqual(self.service.count_active_loans(self.ahmed), 0)

    def test_return_of_book_that_is_not_borrowed(self):
        with self.assertRaises(NotBorrowedError):
            self.service.return_book(self.ahmed, self.book)

    def test_return_view_shows_error_for_other_members_loan(self):
        self.service.borrow_book(self.ahmed, self.book)
        self.client.force_login(self.sara)
        response = self.client.post(reverse("return_book", args=[self.book.pk]), follow=True)
        self.assertContains(response, "only return books that you borrowed")
        self.assertEqual(self.service.count_active_loans(self.ahmed), 1)


class FifoQueueTests(LibraryTestCase):
    def _reserve_at(self, member, hour, minute):
        when = timezone.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        return Reservation.objects.create(book=self.book, member=member, reservation_date=when)

    def test_priority_is_by_reservation_time_not_insertion_order(self):
        self.service.borrow_book(self.staff, self.book)
        
        self._reserve_at(self.omar, 10, 10)
        self._reserve_at(self.ahmed, 10, 0)
        self._reserve_at(self.sara, 10, 5)

        self.assertEqual(self.service.get_next_reservation(self.book).member, self.ahmed)
        self.assertEqual(self.service.get_queue_position(self.ahmed, self.book), 1)
        self.assertEqual(self.service.get_queue_position(self.sara, self.book), 2)
        self.assertEqual(self.service.get_queue_position(self.omar, self.book), 3)

    def test_identical_timestamps_use_lowest_id(self):
        when = timezone.now()
        first = Reservation.objects.create(book=self.book, member=self.sara, reservation_date=when)
        second = Reservation.objects.create(book=self.book, member=self.ahmed, reservation_date=when)
        self.assertLess(first.pk, second.pk)
        self.assertEqual(self.service.get_next_reservation(self.book), first)
        self.assertEqual(self.service.get_queue_position(self.ahmed, self.book), 2)

    def test_empty_waiting_list(self):
        self.assertIsNone(self.service.get_next_reservation(self.book))
        self.assertIsNone(self.service.get_queue_position(self.ahmed, self.book))
        self.service.borrow_book(self.ahmed, self.book)
        self.service.return_book(self.ahmed, self.book)  

    def test_full_fifo_flow(self):
        holder = self.staff
        self.service.borrow_book(holder, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.reserve_book(self.sara, self.book)
        self.service.reserve_book(self.omar, self.book)

        self.service.return_book(holder, self.book)
        statuses = {r.member.username: r.status for r in Reservation.objects.filter(book=self.book)}
        self.assertEqual(statuses, {"ahmed": "ready", "sara": "pending", "omar": "pending"})

        with self.assertRaises(ReservedForAnotherMemberError):
            self.service.borrow_book(self.sara, self.book)
        with self.assertRaises(ReservedForAnotherMemberError):
            self.service.borrow_book(self.omar, self.book)

        self.service.borrow_book(self.ahmed, self.book)
        self.assertEqual(Reservation.objects.get(member=self.ahmed).status, Reservation.Status.FULFILLED)

        self.service.return_book(self.ahmed, self.book)
        self.assertEqual(Reservation.objects.get(member=self.sara).status, Reservation.Status.READY)
        self.assertEqual(Reservation.objects.get(member=self.omar).status, Reservation.Status.PENDING)
        self.assertEqual(self.service.get_queue_position(self.sara, self.book), 1)
        self.assertEqual(self.service.get_queue_position(self.omar, self.book), 2)

    def test_member_cannot_skip_queue_even_if_book_is_free(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.reserve_book(self.sara, self.book)
        self.service.return_book(self.staff, self.book)
        with self.assertRaises(ReservedForAnotherMemberError):
            self.service.borrow_book(self.omar, self.book)  

class CancellationTests(LibraryTestCase):
    def test_cancel_pending_reservation(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.reserve_book(self.sara, self.book)

        self.service.cancel_reservation(self.ahmed, self.book)
        self.assertEqual(Reservation.objects.get(member=self.ahmed).status, Reservation.Status.CANCELLED)
        self.assertEqual(self.service.get_queue_position(self.sara, self.book), 1)  

    def test_cancelling_a_ready_reservation_promotes_next_member(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.reserve_book(self.sara, self.book)
        self.service.return_book(self.staff, self.book)  

        self.service.cancel_reservation(self.ahmed, self.book)
        self.assertEqual(Reservation.objects.get(member=self.sara).status, Reservation.Status.READY)
        self.service.borrow_book(self.sara, self.book)  

    def test_cancel_without_reservation(self):
        with self.assertRaises(ReservationNotFoundError):
            self.service.cancel_reservation(self.ahmed, self.book)

    def test_cannot_cancel_twice(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.cancel_reservation(self.ahmed, self.book)
        with self.assertRaises(ReservationNotFoundError):
            self.service.cancel_reservation(self.ahmed, self.book)

    def test_member_can_reserve_again_after_cancelling(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.cancel_reservation(self.ahmed, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.assertEqual(Reservation.objects.filter(member=self.ahmed).count(), 2)

class ReservationRulesTests(LibraryTestCase):
    def test_duplicate_reservation_is_prevented(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        with self.assertRaises(DuplicateReservationError):
            self.service.reserve_book(self.ahmed, self.book)
        self.assertEqual(Reservation.objects.filter(member=self.ahmed, book=self.book).count(), 1)

    def test_cannot_reserve_an_available_book(self):
        with self.assertRaises(BookAvailableError):
            self.service.reserve_book(self.ahmed, self.book)

    def test_cannot_reserve_a_book_you_already_hold(self):
        self.service.borrow_book(self.ahmed, self.book)
        with self.assertRaises(AlreadyBorrowedByMemberError):
            self.service.reserve_book(self.ahmed, self.book)

    def test_reserve_view_flow_with_messages(self):
        self.service.borrow_book(self.staff, self.book)
        self.client.force_login(self.ahmed)
        url = reverse("reserve_book", args=[self.book.pk])
        first = self.client.post(url, follow=True)
        self.assertContains(first, "position 1")
        second = self.client.post(url, follow=True)
        self.assertContains(second, "already have an active reservation")

class OverdueTests(LibraryTestCase):
    def _record(self, borrowed_days_ago, due_days_ago, returned_days_ago=None):
        now = timezone.now()
        return BorrowRecord(
            book=self.book,
            member=self.ahmed,
            borrow_date=now - timedelta(days=borrowed_days_ago),
            due_date=now - timedelta(days=due_days_ago),
            return_date=None if returned_days_ago is None else now - timedelta(days=returned_days_ago),
            status="borrowed" if returned_days_ago is None else "returned",
        )

    def test_not_overdue_before_due_date(self):
        record = self._record(borrowed_days_ago=5, due_days_ago=-9)  
        self.assertEqual(self.service.calculate_overdue_days(record), 0)

    def test_overdue_days_for_active_loan(self):
        record = self._record(borrowed_days_ago=19, due_days_ago=5)
        self.assertEqual(self.service.calculate_overdue_days(record), 5)

    def test_overdue_uses_return_date_for_returned_loan(self):
        record = self._record(borrowed_days_ago=30, due_days_ago=16, returned_days_ago=13)
        self.assertEqual(self.service.calculate_overdue_days(record), 3)

    def test_returned_on_time_is_zero(self):
        record = self._record(borrowed_days_ago=20, due_days_ago=6, returned_days_ago=8)
        self.assertEqual(self.service.calculate_overdue_days(record), 0)

    def test_explicit_now_argument(self):
        record = self.service.borrow_book(self.ahmed, self.book)
        later = record.due_date + timedelta(days=2, hours=3)
        self.assertEqual(self.service.calculate_overdue_days(record, now=later), 2)

class PrivacyAndConstraintTests(LibraryTestCase):
    def test_members_only_see_their_own_borrowings(self):
        self.service.borrow_book(self.ahmed, self.book)
        other = make_book(title="Sara's book")
        self.service.borrow_book(self.sara, other)

        self.client.force_login(self.ahmed)
        response = self.client.get(reverse("my_borrowings"))
        titles = [r.book.title for r in response.context["active"]]
        self.assertEqual(titles, ["Test Book"])

    def test_private_pages_require_login(self):
        for name in ("my_borrowings", "my_reservations", "profile"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)

    def test_my_reservations_shows_queue_position(self):
        self.service.borrow_book(self.staff, self.book)
        self.service.reserve_book(self.ahmed, self.book)
        self.service.reserve_book(self.sara, self.book)
        self.client.force_login(self.sara)
        response = self.client.get(reverse("my_reservations"))
        self.assertEqual(response.context["reservations"][0].position, 2)

    def test_database_prevents_two_active_loans_for_one_book(self):
        from django.db import IntegrityError, transaction

        self.service.borrow_book(self.ahmed, self.book)
        now = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            BorrowRecord.objects.create(
                book=self.book, member=self.sara, borrow_date=now, due_date=now + timedelta(days=14)
            )

    def test_book_status_flags_for_detail_page(self):
        self.service.borrow_book(self.ahmed, self.book)
        status = self.service.get_book_status(self.book, self.ahmed)
        self.assertTrue(status.can_return)
        self.assertFalse(status.can_borrow)
        self.assertFalse(status.can_reserve)

        status = self.service.get_book_status(self.book, self.sara)
        self.assertTrue(status.can_reserve)
        self.assertFalse(status.can_return)