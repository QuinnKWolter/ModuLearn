"""
Custom Django authentication backends for ModuLearn.
"""

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from .knowledgetree_auth import KnowledgeTreeAuthService, KnowledgeTreeAuthError
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class KnowledgeTreeBackend(ModelBackend):
    """
    Custom authentication backend that authenticates against KnowledgeTree.
    
    This backend is used when users check "Sign in with KnowledgeTree credentials"
    on the login form.
    """
    
    def authenticate(self, request, username=None, password=None, use_knowledgetree=False, **kwargs):
        """
        Authenticate user against KnowledgeTree.
        
        This backend is called automatically by Django's authentication system.
        It only attempts KnowledgeTree authentication if explicitly requested
        (via use_knowledgetree=True) to avoid interfering with standard Django auth.
        
        Args:
            request: HTTP request object
            username: Username from login form
            password: Password from login form
            use_knowledgetree: Boolean flag indicating KnowledgeTree authentication requested
            **kwargs: Additional keyword arguments
        
        Returns:
            User object if authentication successful, None otherwise
        """
        # Only attempt KT auth if explicitly requested
        if not use_knowledgetree:
            return None
        
        if username is None or password is None:
            return None
        
        try:
            kt_service = KnowledgeTreeAuthService()
            
            kt_user_data = kt_service.authenticate(username, password)
            
            if not kt_user_data:
                logger.warning(f"KnowledgeTree authentication failed for user: {username}")
                return None
            
            # Get or create ModuLearn user
            user = self._get_or_create_user(kt_user_data)
            
            if user:
                logger.info(f"KnowledgeTree authentication successful for user: {username} (kt_user_id={user.kt_user_id})")
                logger.info(f"Note: /PortalServices/Auth is stateless and does not create HTTP sessions")
                logger.info(f"For accessing protected resources (Show servlet), users will be redirected to KnowledgeTree login if no session exists")
                logger.info(f"This is the recommended approach - browser-based authentication for protected resources")
            
            return user
            
        except KnowledgeTreeAuthError as e:
            logger.error(f"KnowledgeTree authentication error for user {username}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during KnowledgeTree authentication for user {username}: {str(e)}", exc_info=True)
            return None
    
    def _get_or_create_user(self, kt_user_data: dict):
        """
        Get or create ModuLearn user from KnowledgeTree user data.
        
        Handles username conflicts and account linking.
        Uses kt_login (username) as primary identifier since API doesn't provide UserID.
        """
        kt_user_id = kt_user_data.get('user_id')  # May be None if from API
        kt_login = kt_user_data.get('login', '')
        username = kt_login  # Use KT login as ModuLearn username
        
        # Try to find existing user by kt_user_id first (if available)
        if kt_user_id:
            user = User.objects.filter(kt_user_id=kt_user_id).first()
            if user:
                # User exists and is linked to this KT account
                self._update_user_from_kt(user, kt_user_data)
                return user
        
        # Try to find by kt_login (username) - primary matching method
        user = User.objects.filter(kt_login=kt_login).first()
        if user:
            # Update kt_user_id if we have it and user doesn't
            if kt_user_id and not user.kt_user_id:
                user.kt_user_id = kt_user_id
            self._update_user_from_kt(user, kt_user_data)
            user.save()
            return user
        
        # Try to find by username (ModuLearn username)
        user = User.objects.filter(username=username).first()
        if user:
            if user.kt_user_id and kt_user_id and user.kt_user_id != kt_user_id:
                # Username exists and is linked to different KT account
                logger.warning(
                    f"Username conflict: {username} already linked to different KT user (KT ID: {user.kt_user_id})"
                )
                return None  # Security: don't allow linking to different account
            else:
                # Username exists but not linked - link it
                logger.info(f"Linking existing ModuLearn user {username} to KnowledgeTree account")
                if kt_user_id and not user.kt_user_id:
                    user.kt_user_id = kt_user_id
                user.kt_login = kt_login
                self._update_user_from_kt(user, kt_user_data)
                user.save()
                return user
        
        # Create new user - check aggregate.ent_non_student to determine if instructor
        logger.info(f"Creating new ModuLearn user from KnowledgeTree: {username}")
        
        # Check if user is an instructor in aggregate.ent_non_student
        from dashboard.kt_utils import is_user_instructor_in_aggregate
        is_instructor = is_user_instructor_in_aggregate(kt_login)
        
        user = User.objects.create_user(
            username=username,
            email=kt_user_data.get('email', '') or f"{username}@knowledgetree.local",
            full_name=kt_user_data.get('name', '') or username,
            is_instructor=is_instructor,
            is_student=not is_instructor,  # If not instructor, they're a student
        )
        
        if kt_user_id:
            user.kt_user_id = kt_user_id
        user.kt_login = kt_login
        self._update_user_from_kt(user, kt_user_data)
        user.save()
        
        logger.info(f"Created new ModuLearn user {username}: is_instructor={is_instructor}, is_student={not is_instructor}")
        return user
    
    def _update_user_from_kt(self, user, kt_user_data: dict):
        """Update user fields from KnowledgeTree data."""
        # Update name if not set or if KT has better data
        if kt_user_data.get('name') and not user.full_name:
            user.full_name = kt_user_data['name']
        
        # Update email if not set
        if kt_user_data.get('email') and not user.email:
            user.email = kt_user_data['email']
        
        # Update groups
        user.kt_groups = kt_user_data.get('groups', [])
        
        # Update kt_login if changed
        if kt_user_data.get('login'):
            user.kt_login = kt_user_data['login']
        
        # Update instructor/student status based on aggregate.ent_non_student
        # Only update if user has kt_login (needed for the check)
        if user.kt_login:
            from dashboard.kt_utils import is_user_instructor_in_aggregate
            is_instructor = is_user_instructor_in_aggregate(user.kt_login)
            # Only update if status has changed
            if user.is_instructor != is_instructor:
                logger.info(f"Updating user {user.username} instructor status: {user.is_instructor} -> {is_instructor}")
                user.is_instructor = is_instructor
                user.is_student = not is_instructor

