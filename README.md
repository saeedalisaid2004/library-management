# Library Management & Smart Book Reservation System

A Django application where members browse a catalog, borrow and return books, and join a fair
first-in-first-out (FIFO) waiting list when a book is unavailable. All business rules live in a
dedicated `LibraryService` class; views only translate requests and responses.

**Stack:** Python 3.11+, Django 5.1+, PostgreSQL (SQLite optional for quick runs), Django Templates, `django.test.TestCase`.

---

## 1. Setup

```bash
# 1. Virtual environment + dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Start PostgreSQL (Docker is the easiest way)
docker compose up -d db
#   Using your own PostgreSQL instead? Create a database and set the POSTGRES_* variables
#   (see .env.example). Defaults: db=library user=library password=library host=localhost port=5432.

# 3. Create tables, load demo data, run
python manage.py makemigrations library    # first time only; commit the generated files
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

Open http://127.0.0.1:8000/.

Demo accounts created by `seed_data` (also 10 books):

| Role   | Username                | Password      |
|--------|-------------------------|---------------|
| Staff  | `admin`                 | `admin12345`  |
| Member | `ahmed`, `sara`, `omar` | `member12345` |

No PostgreSQL available? Prefix any command with `USE_SQLITE=1` (Windows PowerShell: `$env:USE_SQLITE="1"`).

## 2. Running the tests

```bash
python manage.py test                # PostgreSQL (needs the database running; Django creates test_library)
USE_SQLITE=1 python manage.py test   # no PostgreSQL needed
```

The suite covers all ten required scenarios (registration/login, book creation, successful borrow,
unavailable book, 3-book limit, return, FIFO ordering, cancellation, duplicate reservation,
overdue days) plus edge cases: queue skipping, empty waiting list, tie-break by id, cancelling a
`ready` reservation, returning someone else's book, private pages, deleting a book with an active
loan, and the database-level constraint.

## 3. Database models

```
User (django.contrib.auth) 1 ──< BorrowRecord >── 1 Book
User                       1 ──< Reservation  >── 1 Book
```

| Model | Fields | Notes |
|-------|--------|-------|
| `Book` | title, author, **unique** isbn, category, publication_year, created_at | ISBN: 10/13 digits, hyphens accepted in the form. Year cannot be in the future. |
| `BorrowRecord` | book (FK, `PROTECT`), member (FK User), borrow_date, due_date, return_date (nullable), status `borrowed`/`returned` | One row per loan. History is never deleted. |
| `Reservation` | book (FK), member (FK User), reservation_date, status `pending`/`ready`/`fulfilled`/`cancelled` | One row per place in a waiting list. |

Members use Django's built-in `User` directly — no profile model was needed, so there is no
`OneToOneField`; the relationships are `ForeignKey`s.

**Database constraints** (they protect the rules even if the service layer is bypassed):

* `unique_active_loan_per_book` — partial unique index on `book` where `status='borrowed'`: one copy can't be on loan to two members.
* `unique_active_reservation_per_member_book` — partial unique index on `(book, member)` where status is `pending`/`ready`: no duplicate active reservations.
* `due_date > borrow_date`, and `status='returned'` ⇔ `return_date IS NOT NULL`.
* `Book.isbn` unique.

**Why `PROTECT` on `BorrowRecord.book`?** Deleting a book would silently erase loan history, so the
database refuses it. `Reservation.book` is `CASCADE` (reservations are meaningless without the book).

## 4. How the FIFO reservation algorithm works

The waiting list of a book is its **active reservations** (`pending` or `ready`).

* **Priority** = `(reservation_date, id)` — earliest time first; if times are identical the lowest id wins.
* `LibraryService._ordered_queue(book)` loads the active reservations and sorts them by that key in
  plain Python. The head of the list is `get_next_reservation(book)`; a member's position is their
  index + 1. No queue library is used.

| Event | What happens |
|-------|--------------|
| Member reserves a borrowed book | Added to the list as `pending` (duplicates rejected). |
| Book is returned | The head of the list becomes `ready`. |
| Someone tries to borrow | Allowed only if there is no list, or **they are the head**. Otherwise `ReservedForAnotherMemberError` — nobody can skip the queue. |
| Head borrows the book | Their reservation becomes `fulfilled`. |
| Their loan is returned | The next member becomes `ready`. |
| A `ready` reservation is cancelled | The next member becomes `ready` immediately. |
| Waiting list empty | `get_next_reservation` returns `None`; returning a book just frees it. |

Example (Ahmed 10:00, Sara 10:05, Omar 10:10): return → Ahmed `ready` → Ahmed borrows (`fulfilled`) →
Ahmed returns → Sara `ready` → Omar still `pending`, now position 1 → ...

## 5. OOP structure and service-layer design

```
library/
├── models.py      data + database constraints only
├── exceptions.py  LibraryError and specific subclasses (one per business rule)
├── services.py    LibraryService  ← ALL business rules
├── forms.py       Registration, Book (ModelForm), Search forms
├── views.py       thin: call the service, add a flash message, render/redirect
└── tests.py
```

`LibraryService` public methods: `borrow_book`, `return_book`, `reserve_book`, `cancel_reservation`,
`get_next_reservation`, `calculate_overdue_days` (as required) plus `get_queue_position`,
`get_book_status`, `delete_book`, `count_active_loans`, `member_summary`.

* **Encapsulation:** rules and constants (`MAX_ACTIVE_LOANS = 3`, `LOAN_DURATION_DAYS = 14`) live in the
  class; helpers such as `_lock_book`, `_active_loan`, `_ordered_queue`, `_promote_next` are private.
* **Single responsibility:** models store data, the service decides, views handle HTTP, templates display.
* **Reusability:** `_promote_next` is used by both *return* and *cancel*; `_ordered_queue` is the single
  source of truth for ordering and positions.
* **Exception handling:** violations raise specific `LibraryError` subclasses; views catch the base class
  and show `str(exc)` as an error message, so users never see a traceback. The exception hierarchy is
  only for catching them as a group — inheritance is not used elsewhere.
* **Concurrency (bonus E):** every state-changing method runs inside `transaction.atomic()` and locks the
  book row with `select_for_update()`; the partial unique index is a second safety net.

### ORM techniques used

`get()` for rows that must exist (`_lock_book`), `filter().first()` for optional ones (`_active_loan`),
`order_by` / `Meta.ordering`, `Count(..., filter=Q(...), distinct=True)` on the catalog page,
`aggregate()` on the profile page, `select_related()` for loan/reservation lists, and `Q` objects for search.

## 6. Pages

| Page | URL |
|------|-----|
| Catalog (search/filter) | `/` |
| Book detail (borrow / reserve / cancel / return) | `/books/<id>/` |
| Add / edit / delete book (staff) | `/books/add/`, `/books/<id>/edit/`, `/books/<id>/delete/` |
| My Borrowings (active, history, overdue) | `/my/borrowings/` |
| My Reservations (queue positions) | `/my/reservations/` |
| Register / Login / Profile | `/accounts/register/`, `/accounts/login/`, `/accounts/profile/` |
| Django admin | `/admin/` |

Borrow/return/reserve/cancel are POST-only with CSRF protection.

## 7. Assumptions and limitations

* One physical copy per book (as specified). Multiple copies (bonus D) are not implemented.
* A `ready` reservation does not expire automatically; the member (or staff via admin) must cancel it to release the book. A timeout would be a natural next step.
* If the member at the head of the queue already holds 3 books, the book waits for them until they free a slot or cancel.
* Staff can return a book on behalf of a member; members can only return their own.
* Overdue days are whole 24-hour periods after the due timestamp. No fines are calculated.
* The waiting list shows only its size to other members (no names, for privacy).
* REST API (bonus A) and a full Docker image (bonus B) are not included; `docker-compose.yml` only starts PostgreSQL (bonus C).

## 8. Screenshots

Add your screenshots to a `screenshots/` folder and link them here (catalog, book detail, my borrowings, my reservations, admin).
