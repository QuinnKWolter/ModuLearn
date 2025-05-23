from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User

class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        max_length=254,
        required=True,
        help_text='We\'ll never share your email with anyone else.'
    )
    full_name = forms.CharField(max_length=100, required=True, label='Full Name')
    is_instructor = forms.BooleanField(required=False, label='Instructor')
    is_student = forms.BooleanField(required=False, label='Student', initial=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'password1', 'password2', 'is_instructor', 'is_student')

class LoginForm(AuthenticationForm):
    class Meta:
        model = User
        fields = ('username', 'password')

