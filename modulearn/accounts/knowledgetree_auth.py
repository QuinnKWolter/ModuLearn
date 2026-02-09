"""
KnowledgeTree Authentication Service

This module provides authentication against KnowledgeTree using either:
1. REST API (preferred) - /PortalServices/Auth endpoint
2. Direct database access (fallback) - MySQL connection to ent_user table
"""

import hashlib
import logging
import requests
from typing import Optional, Dict, Any
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class KnowledgeTreeAuthError(Exception):
    """Base exception for KnowledgeTree authentication errors"""
    pass


class KnowledgeTreeAPIConnectionError(KnowledgeTreeAuthError):
    """Raised when API connection fails"""
    pass


class KnowledgeTreeAuthenticationFailed(KnowledgeTreeAuthError):
    """Raised when authentication fails"""
    pass


class KnowledgeTreeAuthService:
    """
    Service for authenticating users against KnowledgeTree.
    
    Supports both REST API and direct database authentication methods.
    """
    
    def __init__(self):
        self.config = getattr(settings, 'KNOWLEDGETREE', {})
        self.api_url = self.config.get('API_URL', 'http://adapt2.sis.pitt.edu')
        self.api_timeout = self.config.get('API_TIMEOUT', 10)
        self.auth_method = self.config.get('AUTH_METHOD', 'api')
        self.auth_fallback = self.config.get('AUTH_FALLBACK', True)
        self.auth_enabled = self.config.get('AUTH_ENABLED', True)
        # Note: We do NOT use j_security_check - it's browser-only FORM auth
        # We use /PortalServices/Auth exclusively for programmatic authentication
        
    def _md5_hash(self, password: str) -> str:
        """Hash password using MD5 (no salt, as per KnowledgeTree implementation)"""
        return hashlib.md5(password.encode('utf-8')).hexdigest()
    
    def _check_rate_limit(self, username: str, max_attempts: int = 5, window_minutes: int = 15) -> None:
        """Check if user has exceeded rate limit for authentication attempts"""
        cache_key = f"kt_auth_attempts_{username.lower()}"
        attempts = cache.get(cache_key, 0)
        
        if attempts >= max_attempts:
            logger.warning(f"Rate limit exceeded for user: {username}")
            raise ValidationError(
                f"Too many failed login attempts. Please try again in {window_minutes} minutes."
            )
        
        # Increment attempt counter
        cache.set(cache_key, attempts + 1, timeout=window_minutes * 60)
    
    def _reset_rate_limit(self, username: str) -> None:
        """Reset rate limit counter after successful authentication"""
        cache_key = f"kt_auth_attempts_{username.lower()}"
        cache.delete(cache_key)
    
    # DEPRECATED: This method attempted to use j_security_check for server-side session establishment.
    # j_security_check is browser-only FORM auth and is NOT designed for programmatic use.
    # It consistently fails with 408 timeouts because it's intentionally hostile to non-browser clients.
    #
    # CORRECT APPROACH:
    # - Use /PortalServices/Auth for authentication (stateless, JSON-based) ✅ Already implemented
    # - For protected resources (Show servlet), redirect users to KnowledgeTree login page
    # - Browser authenticates via j_security_check (this is the correct way)
    # - KnowledgeTree sets JSESSIONID cookie in browser
    # - Proxy forwards JSESSIONID cookie to access protected resources
    #
    # This method is kept for reference but should NOT be called.
    def establish_http_session(self, username: str, password: str) -> Optional[Dict[str, str]]:
        """
        DEPRECATED: Do not use this method.
        
        j_security_check is browser-only FORM authentication and is NOT designed for
        programmatic use. It consistently fails with 408 timeouts.
        
        Use /PortalServices/Auth for authentication instead (already implemented in authenticate()).
        For protected resources, redirect users to KnowledgeTree login page for browser-based authentication.
        """
        logger.warning(f"establish_http_session() called but is DEPRECATED")
        logger.warning(f"j_security_check is browser-only and should not be used programmatically")
        logger.warning(f"Use /PortalServices/Auth for authentication (already implemented)")
        logger.warning(f"For protected resources, redirect to KnowledgeTree login page")
        return None
    
    def authenticate_via_api(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user via KnowledgeTree REST API (/PortalServices/Auth).
        
        Uses GET request with usr (username) and pwd (MD5 hash of password) parameters.
        
        Documentation: http://adapt2.sis.pitt.edu/PortalServices/Auth?usr=username&pwd=md5hash
        
        Returns user data dict if successful, None if failed.
        Raises KnowledgeTreeAPIConnectionError on connection errors.
        """
        if not self.auth_enabled:
            return None
        
        # Hash password with MD5 (no salt, as per KnowledgeTree spec)
        password_hash = self._md5_hash(password)
        
        # PortalServices/Auth endpoint
        api_endpoint = f"{self.api_url}/PortalServices/Auth"
        
        try:
            # GET request with usr and pwd parameters
            params = {
                'usr': username,
                'pwd': password_hash  # MD5 hash
            }
            
            logger.debug(f"Attempting KT API authentication for user: {username}")
            logger.debug(f"GET {api_endpoint}?usr={username}&pwd=***")
            
            response = requests.get(
                api_endpoint,
                params=params,
                timeout=self.api_timeout,
                verify=True,  # Verify SSL certificates
            )
            
            response.raise_for_status()
            
            # Log response summary (detailed logging only if needed)
            logger.info(f"KT API Response - Status: {response.status_code}, Cookies: {len(response.cookies)} found")
            set_cookie_header = response.headers.get('Set-Cookie', '')
            if set_cookie_header:
                logger.info(f"KT API Response - Set-Cookie header present")
            
            # Parse JSON response
            try:
                data = response.json()
                logger.info(f"KT API authentication successful: user={data.get('usr', 'unknown')}, loggedin={data.get('loggedin', False)}")
            except ValueError as e:
                # Try to parse as JavaScript object (might not be valid JSON)
                response_text = response.text.strip()
                logger.debug(f"Response text: {response_text[:500]}")
                logger.info(f"KT API Response - Raw text (first 500 chars): {response_text[:500]}")
                
                # Sometimes the response might be JavaScript object notation, not JSON
                # Try to extract values manually if JSON parsing fails
                if 'loggedin' in response_text:
                    # Try to extract values using regex or string parsing
                    import re
                    loggedin_match = re.search(r'loggedin:\s*(true|false)', response_text, re.IGNORECASE)
                    error_match = re.search(r'error:\s*"([^"]*)"', response_text)
                    usr_match = re.search(r'usr:\s*"([^"]*)"', response_text)
                    name_match = re.search(r'name:\s*"([^"]*)"', response_text)
                    email_match = re.search(r'email:\s*"([^"]*)"', response_text)
                    
                    data = {
                        'loggedin': loggedin_match.group(1).lower() == 'true' if loggedin_match else False,
                        'error': error_match.group(1) if error_match else '',
                        'usr': usr_match.group(1) if usr_match else username,
                        'name': name_match.group(1) if name_match else '',
                        'email': email_match.group(1) if email_match else '',
                        'groups': [],  # Groups parsing would be more complex
                    }
                else:
                    raise ValueError(f"Response is not valid JSON and doesn't contain 'loggedin' field: {response_text[:200]}")
            
            logger.debug(f"Parsed response: loggedin={data.get('loggedin')}, error={data.get('error')}")
            
            if data.get('loggedin', False):
                logger.info(f"KT API authentication successful: user={username}")
                return {
                    'user_id': None,  # API doesn't provide UserID, only username
                    'name': data.get('name', '') or username,  # Use name if available, fallback to username
                    'email': data.get('email', '') or '',
                    'groups': data.get('groups', []),
                    'login': data.get('usr', username),  # Use usr from response
                }
            else:
                error_msg = data.get('error', 'Unknown error')
                logger.warning(f"KT API authentication failed: user={username}, error={error_msg}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"KT API timeout for user: {username}")
            raise KnowledgeTreeAPIConnectionError("Authentication service timeout")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"KT API connection error for user: {username}: {str(e)}")
            raise KnowledgeTreeAPIConnectionError("Unable to connect to authentication service")
        except requests.exceptions.HTTPError as e:
            logger.error(f"KT API HTTP error for user: {username}: {str(e)}")
            raise KnowledgeTreeAPIConnectionError(f"Authentication service HTTP error: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"KT API request error for user: {username}: {str(e)}")
            raise KnowledgeTreeAPIConnectionError(f"Authentication service error: {str(e)}")
        except ValueError as e:
            logger.error(f"KT API response parsing error for user: {username}: {str(e)}")
            logger.error(f"Response text: {response.text[:500] if 'response' in locals() else 'N/A'}")
            raise KnowledgeTreeAPIConnectionError("Invalid response from authentication service")
        except Exception as e:
            logger.error(f"KT API unexpected error for user: {username}: {str(e)}", exc_info=True)
            raise KnowledgeTreeAPIConnectionError(f"Authentication error: {str(e)}")
    
    def authenticate_via_database(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user via direct database access to KnowledgeTree.
        Uses SSH tunneling if configured (for development).
        
        Returns user data dict if successful, None if failed.
        """
        if not self.auth_enabled:
            return None
        
        try:
            from dashboard.kt_db_connection import get_paws_db_connection
            from django.conf import settings
            
            password_hash = self._md5_hash(password)
            
            # Get database connection (handles SSH tunneling if needed)
            db_conn = get_paws_db_connection()
            success, message = db_conn.connect()
            
            if not success:
                logger.error(f"Failed to connect to PAWS database for authentication: {message}")
                return None
            
            try:
                connection = db_conn.get_connection()
                db_config = getattr(settings, 'PAWS_DATABASE', {})
                kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
                
                with connection.cursor() as cursor:
                    # Query user with isGroup = 0 to ensure we're authenticating actual users
                    sql = f"""
                        SELECT UserID, Login, Name, Pass, email
                        FROM `{kt_schema}`.ent_user
                        WHERE Login = %s AND isGroup = 0
                    """
                    cursor.execute(sql, (username,))
                    user_row = cursor.fetchone()
                    
                    if not user_row:
                        logger.warning(f"KT DB authentication failed: user not found in KnowledgeTree: {username}")
                        logger.info(f"User '{username}' does not exist in KnowledgeTree database (ent_user table)")
                        return None
                    
                    logger.info(f"User '{username}' found in KnowledgeTree database (UserID: {user_row['UserID']})")
                    
                    stored_hash = user_row['Pass']
                    if stored_hash and stored_hash.lower() == password_hash.lower():
                        logger.info(f"KT DB authentication successful: user={username}, kt_user_id={user_row['UserID']}")
                        
                        # Get user groups
                        groups = []
                        try:
                            groups_sql = f"""
                                SELECT u.Name
                                FROM `{kt_schema}`.rel_user_user ruu
                                LEFT JOIN `{kt_schema}`.ent_user u ON u.UserID = ruu.ParentUserID
                                WHERE ruu.ChildUserID = %s
                            """
                            cursor.execute(groups_sql, (user_row['UserID'],))
                            group_rows = cursor.fetchall()
                            groups = [row['Name'] for row in group_rows if row['Name']]
                        except Exception as e:
                            logger.warning(f"Error fetching KT groups for user {username}: {str(e)}")
                        
                        return {
                            'user_id': user_row['UserID'],
                            'name': user_row['Name'] or '',
                            'email': user_row.get('email', '') or '',
                            'groups': groups,
                            'login': user_row['Login'],
                        }
                    else:
                        logger.warning(f"KT DB authentication failed: wrong password for user: {username}")
                        return None
                        
            finally:
                db_conn.disconnect()
                
        except ImportError as e:
            logger.error(f"Failed to import database connection utilities: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"KT DB authentication error for user: {username}: {str(e)}", exc_info=True)
            return None
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user against KnowledgeTree.
        
        Tries API first, falls back to database if configured.
        
        Returns user data dict if successful, None if failed.
        """
        if not self.auth_enabled:
            return None
        
        # Check rate limiting
        try:
            self._check_rate_limit(username)
        except ValidationError:
            raise
        
        user_data = None
        
        # Try API first if method is 'api' or 'both'
        if self.auth_method in ('api', 'both'):
            try:
                user_data = self.authenticate_via_api(username, password)
                if user_data:
                    self._reset_rate_limit(username)
                    return user_data
            except KnowledgeTreeAPIConnectionError:
                # If API fails and fallback is enabled, try database
                if self.auth_fallback and self.auth_method == 'api':
                    logger.info(f"KT API failed, falling back to database for user: {username}")
                    user_data = self.authenticate_via_database(username, password)
                    if user_data:
                        self._reset_rate_limit(username)
                        return user_data
                else:
                    raise
        
        # Try database if method is 'database' or 'both'
        if self.auth_method in ('database', 'both') and not user_data:
            user_data = self.authenticate_via_database(username, password)
            if user_data:
                self._reset_rate_limit(username)
                return user_data
        
        # Authentication failed
        return None
    
    def check_user_exists_in_database(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Check if a user exists in KnowledgeTree database (without password verification).
        Uses SSH tunneling if configured (for development).
        
        Returns user data dict if found, None if not found.
        """
        if not self.auth_enabled:
            return None
        
        try:
            from dashboard.kt_db_connection import get_paws_db_connection
            from django.conf import settings
            
            # Get database connection (handles SSH tunneling if needed)
            db_conn = get_paws_db_connection()
            success, message = db_conn.connect()
            
            if not success:
                logger.debug(f"Failed to connect to PAWS database to check user existence: {message}")
                return None
            
            try:
                connection = db_conn.get_connection()
                db_config = getattr(settings, 'PAWS_DATABASE', {})
                kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
                
                with connection.cursor() as cursor:
                    sql = f"""
                        SELECT UserID, Login, Name, email
                        FROM `{kt_schema}`.ent_user
                        WHERE Login = %s AND isGroup = 0
                    """
                    cursor.execute(sql, (username,))
                    user_row = cursor.fetchone()
                    
                    if user_row:
                        return {
                            'user_id': user_row['UserID'],
                            'name': user_row['Name'] or '',
                            'email': user_row.get('email', '') or '',
                            'login': user_row['Login'],
                        }
                    return None
                    
            finally:
                db_conn.disconnect()
                
        except ImportError as e:
            logger.debug(f"Failed to import database connection utilities: {str(e)}")
            return None
        except Exception as e:
            logger.debug(f"Error checking if KT user exists '{username}': {str(e)}")
            return None
    
    def create_user_in_database(self, username: str, password: str, email: str = '', full_name: str = '') -> Optional[Dict[str, Any]]:
        """
        Create a new user in KnowledgeTree database (ent_user table).
        Uses SSH tunneling if configured (for development).
        
        This is called when a user successfully authenticates with Django but doesn't exist in KnowledgeTree.
        
        Args:
            username: Username/login for the new user
            password: Plaintext password (will be MD5 hashed)
            email: Email address (optional)
            full_name: Full name (optional, defaults to username)
        
        Returns:
            User data dict with user_id if successful, None if failed.
        """
        logger.info(f"[KT User Creation] Attempting to create KnowledgeTree user '{username}'")
        
        if not self.auth_enabled:
            logger.warning("[KT User Creation] KnowledgeTree authentication not enabled")
            return None
        
        try:
            from dashboard.kt_db_connection import get_paws_db_connection
            from django.conf import settings
            import pymysql
            
            # Get database connection (handles SSH tunneling if needed)
            db_conn = get_paws_db_connection()
            success, message = db_conn.connect()
            
            if not success:
                logger.error(f"[KT User Creation] Failed to connect to PAWS database: {message}")
                return None
            
            try:
                connection = db_conn.get_connection()
                db_config = getattr(settings, 'PAWS_DATABASE', {})
                kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
                
                with connection.cursor() as cursor:
                    # First check if user already exists
                    check_sql = f"""
                        SELECT UserID, Login
                        FROM `{kt_schema}`.ent_user
                        WHERE Login = %s AND isGroup = 0
                    """
                    cursor.execute(check_sql, (username,))
                    existing_user = cursor.fetchone()
                    
                    if existing_user:
                        logger.info(f"[KT User Creation] User '{username}' already exists in KnowledgeTree (UserID: {existing_user['UserID']})")
                        return {
                            'user_id': existing_user['UserID'],
                            'name': full_name or username,
                            'email': email or '',
                            'groups': [],
                            'login': username,
                        }
                    
                    # Insert new user
                    # UserID is auto-increment, so we don't specify it
                    # Based on example row: URI='', Login=username, Name=full_name, Pass=MD5(password),
                    # IsGroup='0', Sync='1', EMail=email, Organization='', City='', Country='', How='',
                    # IsInstructor='0', passActivatedByEmail='', keyActivatedByEmail=''
                    insert_sql = f"""
                        INSERT INTO `{kt_schema}`.ent_user 
                        (URI, Login, Name, Pass, IsGroup, Sync, EMail, Organization, City, Country, How, IsInstructor, passActivatedByEmail, keyActivatedByEmail)
                        VALUES (%s, %s, %s, MD5(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    values = (
                        '',  # URI
                        username,  # Login
                        full_name or username,  # Name
                        password,  # Pass (will be MD5 hashed by SQL)
                        '0',  # IsGroup
                        '1',  # Sync
                        email or '',  # EMail
                        '',  # Organization
                        '',  # City
                        '',  # Country
                        'ModuLearn',  # How
                        '0',  # IsInstructor (default to student)
                        '',  # passActivatedByEmail
                        '',  # keyActivatedByEmail
                    )
                    
                    logger.info(f"[KT User Creation] Executing INSERT for user '{username}'")
                    cursor.execute(insert_sql, values)
                    connection.commit()
                    
                    # Get the auto-generated UserID
                    new_user_id = cursor.lastrowid
                    
                    logger.info(f"[KT User Creation] Successfully created KnowledgeTree user '{username}' with UserID: {new_user_id}")
                    
                    return {
                        'user_id': new_user_id,
                        'name': full_name or username,
                        'email': email or '',
                        'groups': [],
                        'login': username,
                    }
                    
            except pymysql.Error as e:
                connection.rollback()
                logger.error(f"[KT User Creation] Database error creating KT user '{username}': {str(e)}", exc_info=True)
                return None
            finally:
                db_conn.disconnect()
                
        except ImportError as e:
            logger.error(f"[KT User Creation] Failed to import database connection utilities: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"[KT User Creation] Error creating KT user '{username}': {str(e)}", exc_info=True)
            return None

