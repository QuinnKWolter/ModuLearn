from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, AuthenticationForm
from django.contrib import messages

def signup(request):
    """
    Handles user signup.
    """
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_instructor = form.cleaned_data.get('is_instructor', False)
            user.is_student = form.cleaned_data.get('is_student', True)
            user.save()
            login(request, user)
            messages.success(request, 'Registration successful.')
            return redirect('dashboard:student_dashboard' if user.is_student else 'dashboard:instructor_dashboard')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})

def login_view(request):
    """
    Handles user login.
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('main:home')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('main:home')

@login_required
def profile_view(request):
    """
    Displays the user's profile.
    """
    return render(request, 'accounts/profile.html')
