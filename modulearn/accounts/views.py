from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from .forms import SignUpForm, LoginForm, ProfileEditForm, PasswordChangeFormCustom, KnowledgeTreePasswordResetForm
import logging

logger = logging.getLogger(__name__)

def signup(request):
    """
    Handles user signup.
    """
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.full_name = form.cleaned_data.get('full_name', '')
            user.is_instructor = form.cleaned_data.get('is_instructor', False)
            user.is_student = form.cleaned_data.get('is_student', True)
            user.save()
            # Specify the backend when logging in (required when multiple backends are configured)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Registration successful.')
            return redirect('dashboard:student_dashboard' if user.is_student else 'dashboard:instructor_dashboard')
    else:
        form = SignUpForm()
    return render(request, 'accounts/signup.html', {'form': form})

def login_view(request):
    """
    Handles user login with automatic KnowledgeTree authentication fallback.
    If Django authentication fails, automatically tries KnowledgeTree.
    """
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        
        if form.is_valid():
            # Standard Django authentication succeeded
            login(request, form.get_user())
            messages.success(request, 'Successfully signed in.')
            return redirect('main:home')
        else:
            # Standard Django authentication failed - try KnowledgeTree automatically
            kt_config = getattr(settings, 'KNOWLEDGETREE', {})
            if kt_config.get('AUTH_ENABLED', True):
                try:
                    from .backends import KnowledgeTreeBackend
                    
                    user = authenticate(
                        request=request,
                        username=username,
                        password=password,
                        use_knowledgetree=True
                    )
                    
                    if user is not None:
                        login(request, user)
                        messages.success(request, 'Successfully signed in with your KnowledgeTree account.')
                        return redirect('main:home')
                    else:
                        # Both Django and KnowledgeTree authentication failed
                        messages.error(request, 'Invalid username or password.')
                except Exception as e:
                    logger.error(f"Error during KnowledgeTree authentication: {str(e)}", exc_info=True)
                    # Check if it's a connection error
                    error_msg = str(e)
                    if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                        messages.error(request, 'Authentication service temporarily unavailable. Please try again later.')
                    else:
                        messages.error(request, 'Invalid username or password.')
            else:
                # KnowledgeTree authentication disabled
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('main:home')

@login_required
def profile_view(request):
    """
    Displays and allows editing of the user's profile.
    """
    profile_form = ProfileEditForm(instance=request.user)
    password_form = PasswordChangeFormCustom(user=request.user)
    
    # KnowledgeTree password reset form (only for KT users)
    kt_password_form = None
    is_kt_user = bool(request.user.kt_login or request.user.kt_user_id)
    if is_kt_user:
        kt_password_form = KnowledgeTreePasswordResetForm(user=request.user)
    
    # Fetch KnowledgeTree groups with course_ids and MasteryGrids node IDs
    # Only show groups for instructors (students should not see courses in profile)
    legacy_groups = []
    if request.user.is_instructor and (request.user.kt_login or request.user.kt_user_id):
        try:
            from dashboard.kt_utils import get_user_groups_with_masterygrids_nodes
            legacy_groups = get_user_groups_with_masterygrids_nodes(request.user)
        except Exception as e:
            logger.warning(f"Failed to fetch legacy groups for profile: {str(e)}")
            legacy_groups = []
    
    if request.method == 'POST':
        if 'update_profile' in request.POST:
            profile_form = ProfileEditForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('accounts:profile')
        elif 'change_password' in request.POST:
            password_form = PasswordChangeFormCustom(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Password changed successfully.')
                return redirect('accounts:profile')
        elif 'reset_kt_password' in request.POST and is_kt_user:
            kt_password_form = KnowledgeTreePasswordResetForm(user=request.user, data=request.POST)
            if kt_password_form.is_valid():
                try:
                    # Save password in ModuLearn (via form)
                    new_password = kt_password_form.save()
                    
                    # Update password in KnowledgeTree
                    from dashboard.kt_utils import update_kt_password
                    kt_login = request.user.kt_login or request.user.username
                    kt_success, kt_message = update_kt_password(kt_login, new_password)
                    
                    if kt_success:
                        # Update session auth hash to keep user logged in
                        update_session_auth_hash(request, request.user)
                        messages.success(request, 'Password reset successfully in both ModuLearn and KnowledgeTree.')
                        logger.info(f"Password reset successful for KT user {kt_login}")
                    else:
                        # ModuLearn password was updated, but KT update failed
                        messages.warning(request, f'Password updated in ModuLearn, but KnowledgeTree update failed: {kt_message}. Please contact support.')
                        logger.error(f"KT password update failed for {kt_login}: {kt_message}")
                    
                    return redirect('accounts:profile')
                except Exception as e:
                    logger.error(f"Error during KT password reset: {str(e)}", exc_info=True)
                    messages.error(request, f'Error resetting password: {str(e)}')
    
    return render(request, 'accounts/profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'kt_password_form': kt_password_form,
        'is_kt_user': is_kt_user,
        'legacy_groups': legacy_groups,  # Pass groups with course_ids for MasteryGrids links
    })
