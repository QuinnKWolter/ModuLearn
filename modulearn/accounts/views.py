from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm
from django.contrib import messages

def signup(request):
    """
    Handles user signup.
    """
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # Set user role based on form input or default to student
            user.is_student = True
            user.save()
            login(request, user)
            messages.success(request, 'Registration successful.')
            return redirect('dashboard:student_dashboard')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})

@login_required
def profile_view(request):
    """
    Displays the user's profile.
    """
    return render(request, 'accounts/profile.html')
