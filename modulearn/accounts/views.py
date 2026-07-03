from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from .forms import (
    SignUpForm,
    LoginForm,
    ProfileEditForm,
    PasswordChangeFormCustom,
    SetPasswordFormCustom,
    KnowledgeTreePasswordResetForm,
    KnowledgeTreeProvisionForm,
)
import logging
from modulearn.core.roles import get_legacy_masterygrids_groups, get_user_role_snapshot
from recruitment.services.participants import participant_course_redirect

logger = logging.getLogger(__name__)

def _default_full_name_for_user(user) -> str:
    """
    Best-effort display name. Uses email local-part if available, else username.
    """
    if getattr(user, 'full_name', None):
        return user.full_name
    email = getattr(user, 'email', '') or ''
    if '@' in email:
        local = email.split('@', 1)[0].strip()
        return local or (user.username or '')
    return user.username or ''


def _ensure_kt_user_exists(user, password: str):
    """
    Ensure user exists in KnowledgeTree database. If not, create them.
    
    This is called after successful Django authentication (sign in/sign up)
    to automatically create a corresponding KnowledgeTree user entry.
    
    Args:
        user: Django User object
        password: Plaintext password (for creating KT user with same password)
    """
    logger.info(f"[KT User Creation] Checking KnowledgeTree user for '{user.username}'")
    
    # Skip if user already has KnowledgeTree credentials
    if user.kt_user_id or user.kt_login:
        logger.info(f"[KT User Creation] User {user.username} already has KnowledgeTree credentials (kt_user_id={user.kt_user_id}, kt_login={user.kt_login}) - skipping creation")
        return
    
    # Check if KnowledgeTree auth is enabled
    kt_config = getattr(settings, 'KNOWLEDGETREE', {})
    if not kt_config.get('AUTH_ENABLED', True):
        logger.warning("[KT User Creation] KnowledgeTree authentication disabled - skipping user creation")
        return
    
    try:
        from .knowledgetree_auth import KnowledgeTreeAuthService
        
        kt_service = KnowledgeTreeAuthService()
        
        # Check if PAWS database is configured
        db_config = getattr(settings, 'PAWS_DATABASE', {})
        if not db_config or not db_config.get('HOST'):
            logger.warning("[KT User Creation] PAWS database not configured - cannot check/create user")
            return
        
        logger.info(f"[KT User Creation] KnowledgeTree database configured - checking if user '{user.username}' exists")
        
        # Check if user exists in KnowledgeTree database (without password verification)
        kt_user_data = kt_service.check_user_exists_in_database(user.username)
        
        if kt_user_data:
            # User exists in KnowledgeTree - link the accounts
            logger.info(f"[KT User Creation] User '{user.username}' found in KnowledgeTree (UserID: {kt_user_data.get('user_id')})")
            user.kt_user_id = kt_user_data.get('user_id')
            user.kt_login = kt_user_data.get('login', user.username)
            user.save()
            logger.info(f"[KT User Creation] Linked Django user '{user.username}' to KnowledgeTree account")
        else:
            # User doesn't exist in KnowledgeTree - create them
            logger.info(f"[KT User Creation] User '{user.username}' not found in KnowledgeTree - creating new entry")
            logger.info(f"[KT User Creation] Creating user with email='{user.email or ''}', full_name='{user.full_name or user.username}'")
            
            if not password:
                logger.error(f"[KT User Creation] Cannot create KnowledgeTree user for '{user.username}': password is empty")
                return
            
            kt_user_data = kt_service.create_user_in_database(
                username=user.username,
                password=password,
                email=user.email or '',
                full_name=user.full_name or user.username
            )
            
            if kt_user_data:
                # Link the accounts
                user.kt_user_id = kt_user_data.get('user_id')
                user.kt_login = kt_user_data.get('login', user.username)
                user.save()
                logger.info(f"[KT User Creation] Successfully created KnowledgeTree user '{user.username}' (UserID: {kt_user_data.get('user_id')}) and linked to Django account")
            else:
                logger.error(f"[KT User Creation] Failed to create KnowledgeTree user for '{user.username}' - create_user_in_database returned None")
                
    except Exception as e:
        logger.error(f"[KT User Creation] Error ensuring KnowledgeTree user exists for '{user.username}': {str(e)}", exc_info=True)
        # Don't fail authentication if KT user creation fails


def signup(request):
    """
    Handles user signup.
    """
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.full_name = form.cleaned_data.get('full_name', '')
            selected_role = form.cleaned_data.get('role', 'student')
            user.is_instructor = selected_role == 'instructor'
            user.is_student = selected_role == 'student'
            user.save()
            
            # Get password from form before saving (form.save() may clear it)
            password = form.cleaned_data.get('password1')
            
            # Specify the backend when logging in (required when multiple backends are configured)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            # Check if user exists in KnowledgeTree, create if not
            _ensure_kt_user_exists(user, password)
            
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
            user = form.get_user()
            login(request, user)
            
            # Check if user exists in KnowledgeTree, create if not
            _ensure_kt_user_exists(user, password)
            
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
                        
                        # User authenticated via KnowledgeTree, so they definitely exist there
                        # No need to create them
                        
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
    redirect_response = participant_course_redirect(request.user)
    if redirect_response:
        return redirect_response

    role_snapshot = get_user_role_snapshot(request.user)
    profile_form = ProfileEditForm(instance=request.user)
    # Choose password form:
    # - If user already has a usable password: require current password (PasswordChangeForm)
    # - If user has no usable password yet (Canvas/LTI provisioned): allow setting password without current
    if request.user.has_usable_password():
        password_form = PasswordChangeFormCustom(user=request.user)
        password_form_mode = 'change'
    else:
        password_form = SetPasswordFormCustom(user=request.user)
        password_form_mode = 'set'
    
    # KnowledgeTree password reset form (only for KT users)
    kt_password_form = None
    is_kt_user = bool(request.user.kt_login or request.user.kt_user_id)
    if is_kt_user:
        kt_password_form = KnowledgeTreePasswordResetForm(user=request.user)
    
    # KnowledgeTree provisioning form (only for non-KT users; uses just new password + confirmation)
    kt_provision_form = None
    if not is_kt_user:
        kt_config = getattr(settings, 'KNOWLEDGETREE', {})
        db_config = getattr(settings, 'PAWS_DATABASE', {})
        kt_enabled = kt_config.get('AUTH_ENABLED', True) and bool(db_config and db_config.get('HOST'))
        if kt_enabled:
            kt_provision_form = KnowledgeTreeProvisionForm(user=request.user)
    
    # Fetch KnowledgeTree groups with course_ids and MasteryGrids node IDs
    # Only show groups for instructors (students should not see courses in profile)
    legacy_groups = []
    if role_snapshot["effective_is_instructor"]:
        legacy_groups = get_legacy_masterygrids_groups(request.user)
    
    if request.method == 'POST':
        if 'update_profile' in request.POST:
            profile_form = ProfileEditForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('accounts:profile')
        elif 'change_password' in request.POST:
            if request.user.has_usable_password():
                password_form = PasswordChangeFormCustom(user=request.user, data=request.POST)
            else:
                password_form = SetPasswordFormCustom(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Password changed successfully.')
                return redirect('accounts:profile')
        elif 'provision_kt_user' in request.POST and (not is_kt_user):
            kt_provision_form = KnowledgeTreeProvisionForm(user=request.user, data=request.POST)
            if kt_provision_form.is_valid():
                try:
                    new_password = kt_provision_form.save()
                    # Ensure user has a friendly full_name for KT record
                    request.user.full_name = _default_full_name_for_user(request.user)
                    request.user.save(update_fields=['full_name'])
                    _ensure_kt_user_exists(request.user, new_password)
                    update_session_auth_hash(request, request.user)
                    messages.success(request, 'KnowledgeTree account provisioned successfully.')
                    return redirect('accounts:profile')
                except Exception as e:
                    logger.error(f"Error provisioning KnowledgeTree account: {str(e)}", exc_info=True)
                    messages.error(request, f"Could not provision KnowledgeTree account: {str(e)}")
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
        'kt_provision_form': kt_provision_form,
        'is_kt_user': is_kt_user,
        'password_form_mode': password_form_mode,
        'legacy_groups': legacy_groups,  # Pass groups with course_ids for MasteryGrids links
        'effective_is_student': role_snapshot["effective_is_student"],
        'effective_is_instructor': role_snapshot["effective_is_instructor"],
    })
