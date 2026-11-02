"""Domain exceptions raised by LibraryService.

Views catch LibraryError and show ``str(exc)`` to the user, so every message here is written
to be user-friendly.
"""


class LibraryError(Exception):
    """Base class for every business-rule violation."""


class BookUnavailableError(LibraryError):
    """The book is already on loan."""


class BorrowLimitExceededError(LibraryError):
    """The member already has the maximum number of active loans."""


class ReservedForAnotherMemberError(LibraryError):
    """Someone ahead in the waiting list has priority on this book."""


class NotBorrowedError(LibraryError):
    """Tried to return a book that is not currently on loan."""


class NotLoanOwnerError(LibraryError):
    """Tried to return a book that belongs to another member."""


class DuplicateReservationError(LibraryError):
    """The member already has an active reservation for this book."""


class BookAvailableError(LibraryError):
    """Reservation refused because the book can simply be borrowed."""


class AlreadyBorrowedByMemberError(LibraryError):
    """The member already holds this book, so reserving it makes no sense."""


class ReservationNotFoundError(LibraryError):
    """The member has no active reservation for this book."""


class BookHasActiveLoanError(LibraryError):
    """A book that is currently on loan cannot be deleted."""


class BookHasHistoryError(LibraryError):
    """A book with borrowing history cannot be deleted (history is kept for records)."""
