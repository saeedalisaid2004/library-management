from django.urls import path

from . import views

urlpatterns = [
    path("", views.book_list, name="book_list"),
    path("books/add/", views.book_create, name="book_create"),
    path("books/<int:pk>/", views.book_detail, name="book_detail"),
    path("books/<int:pk>/edit/", views.book_edit, name="book_edit"),
    path("books/<int:pk>/delete/", views.book_delete, name="book_delete"),
    path("books/<int:pk>/borrow/", views.borrow_book, name="borrow_book"),
    path("books/<int:pk>/return/", views.return_book, name="return_book"),
    path("books/<int:pk>/reserve/", views.reserve_book, name="reserve_book"),
    path("books/<int:pk>/cancel-reservation/", views.cancel_reservation, name="cancel_reservation"),
    path("my/borrowings/", views.my_borrowings, name="my_borrowings"),
    path("my/reservations/", views.my_reservations, name="my_reservations"),
    path("accounts/register/", views.register, name="register"),
    path("accounts/profile/", views.profile, name="profile"),
]
