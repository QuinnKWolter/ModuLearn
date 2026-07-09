from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import password_validation
from .email_utils import normalize_email_address
from .models import User

class SignUpForm(UserCreationForm):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('instructor', 'Instructor'),
    )

    email = forms.EmailField(
        max_length=254,
        required=True,
        help_text='We\'ll never share your email with anyone else.'
    )
    full_name = forms.CharField(max_length=100, required=True, label='Full Name')
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial='student',
        widget=forms.RadioSelect,
        label='Role',
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'password1', 'password2', 'role')

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data.get('email'))
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email address already exists.')
        return email

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

    def clean_email(self):
        email = normalize_email_address(self.cleaned_data.get('email'))
        original_email = normalize_email_address(
            User.objects.filter(pk=self.instance.pk).values_list('email', flat=True).first()
        )
        if (
            email != original_email
            and User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email).exists()
        ):
            raise forms.ValidationError('An account with this email address already exists.')
        return email

class PasswordChangeFormCustom(PasswordChangeForm):
    """Custom password change form with better styling."""
    old_password = forms.CharField(
        label="Current password",
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'class': 'form-control'}),
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

class SetPasswordFormCustom(SetPasswordForm):
    """
    Password set form that does NOT require the current password.
    Intended for users who do not yet have a usable password (e.g., Canvas/LTI-provisioned).
    """
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


class KnowledgeTreePasswordResetForm(forms.Form):
    """Form for resetting password in both ModuLearn and KnowledgeTree."""
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
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_new_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")
        return password2
    
    def clean_new_password1(self):
        password1 = self.cleaned_data.get('new_password1')
        if password1:
            # Validate password against Django's password validators
            password_validation.validate_password(password1, self.user)
        return password1
    
    def save(self):
        """Save the new password to both ModuLearn and KnowledgeTree."""
        password = self.cleaned_data['new_password1']
        # Update ModuLearn password
        self.user.set_password(password)
        self.user.save()
        return password


class KnowledgeTreeProvisionForm(KnowledgeTreePasswordResetForm):
    """
    Form for creating/provisioning a KnowledgeTree account for an existing ModuLearn user.
    Uses only new password + confirmation.
    """
    pass
