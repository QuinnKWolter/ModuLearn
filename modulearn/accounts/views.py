from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from .forms import SignUpForm, LoginForm, ProfileEditForm, PasswordChangeFormCustom, KnowledgeTreePasswordResetForm
import logging

logger = logging.getLogger(__name__)


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
            user.is_instructor = form.cleaned_data.get('is_instructor', False)
            user.is_student = form.cleaned_data.get('is_student', True)
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
