"""Create demo users and books:  python manage.py seed_data"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from library.models import Book

BOOKS = [
    ("Clean Code", "Robert C. Martin", "9780132350884", "Programming", 2008),
    ("The Pragmatic Programmer", "Andrew Hunt", "9780135957059", "Programming", 2019),
    ("Fluent Python", "Luciano Ramalho", "9781492056355", "Programming", 2022),
    ("Two Scoops of Django", "Daniel Feldroy", "9780692915721", "Programming", 2020),
    ("Introduction to Algorithms", "Thomas H. Cormen", "9780262046305", "Computer Science", 2022),
    ("Sapiens", "Yuval Noah Harari", "9780062316097", "History", 2015),
    ("Cosmos", "Carl Sagan", "9780345539434", "Science", 2013),
    ("A Brief History of Time", "Stephen Hawking", "9780553380163", "Science", 1998),
    ("1984", "George Orwell", "9780451524935", "Fiction", 1961),
    ("The Alchemist", "Paulo Coelho", "9780062315007", "Fiction", 2014),
]
MEMBERS = ["ahmed", "sara", "omar"]


class Command(BaseCommand):
    help = "Create demo books, a staff account (admin) and three members (ahmed, sara, omar)."

    def handle(self, *args, **options):
        User = get_user_model()

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin12345")
        for name in MEMBERS:
            if not User.objects.filter(username=name).exists():
                User.objects.create_user(name, f"{name}@example.com", "member12345")

        created = 0
        for title, author, isbn, category, year in BOOKS:
            _, was_created = Book.objects.get_or_create(
                isbn=isbn,
                defaults={"title": title, "author": author, "category": category, "publication_year": year},
            )
            created += was_created

        self.stdout.write(self.style.SUCCESS(f"Done. {created} new book(s) created."))
        self.stdout.write("Staff:   admin / admin12345")
        self.stdout.write("Members: ahmed, sara, omar / member12345")
