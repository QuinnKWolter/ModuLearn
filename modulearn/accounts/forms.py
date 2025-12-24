from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from django.contrib.auth import password_validation
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

class ProfileEditForm(forms.ModelForm):
    """Form for editing user profile information."""
    email = forms.EmailField(
        max_length=254,
        required=True,
        help_text='Your email address'
    )
    full_name = forms.CharField(
        max_length=100,
        required=False,
        label='Full Name',
        help_text='Your display name'
    )
    
    class Meta:
        model = User
        fields = ('email', 'full_name')

class PasswordChangeFormCustom(PasswordChangeForm):
    """Custom password change form with better styling."""
    old_password = forms.CharField(
        label="Current password",
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'autofocus': True, 'class': 'form-control'}),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'form-control'}),
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = forms.CharField(
        label="New password confirmation",
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'form-control'}),
    )

