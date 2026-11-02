from django.contrib import admin

from .models import Book, BorrowRecord, Reservation


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "isbn", "category", "publication_year")
    search_fields = ("title", "author", "isbn")
    list_filter = ("category",)


@admin.register(BorrowRecord)
class BorrowRecordAdmin(admin.ModelAdmin):
    list_display = ("book", "member", "borrow_date", "due_date", "return_date", "status")
    list_filter = ("status",)
    list_select_related = ("book", "member")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("book", "member", "reservation_date", "status")
    list_filter = ("status",)
    list_select_related = ("book", "member")
