from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Book

User = get_user_model()


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class BookForm(forms.ModelForm):
    
    isbn = forms.CharField(max_length=17, label="ISBN")

    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "category", "publication_year"]

    def clean_isbn(self):
        
        return self.cleaned_data["isbn"].replace("-", "").replace(" ", "")


class BookSearchForm(forms.Form):
    q = forms.CharField(required=False, label="Title or author")
    category = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = Book.objects.order_by("category").values_list("category", flat=True).distinct()
        self.fields["category"].choices = [("", "All categories")] + [(c, c) for c in categories]
