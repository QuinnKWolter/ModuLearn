"""
KnowledgeTree utility functions for dashboard integration.
Uses direct database queries for optimal performance.
"""

import logging
import pymysql
from typing import List, Dict, Optional, Any
from django.conf import settings
from .kt_db_connection import get_paws_db_connection

logger = logging.getLogger(__name__)


def get_kt_user_id_by_login(kt_login: str) -> Optional[int]:
    """
    Look up KnowledgeTree UserID by username/login.
    
    This is useful when a user was authenticated via API (which doesn't provide UserID)
    and we need to query the database for their groups.
    
    Args:
        kt_login: KnowledgeTree username/login
        
    Returns:
        UserID if found, None otherwise
    """
    if not kt_login:
        logger.warning("get_kt_user_id_by_login called with empty kt_login")
        return None
    
    try:
        # Log configuration for debugging
        from django.conf import settings
        db_config = getattr(settings, 'PAWS_DATABASE', {})
        logger.debug(f"Database config - USE_SSH: {db_config.get('USE_SSH')}, HOST: {db_config.get('HOST')}, SSH_HOST: {db_config.get('SSH_HOST')}, SSH_USER: {db_config.get('SSH_USER')}")
        
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database to look up user: {message}")
            return None
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = f"""
                    SELECT UserID
                    FROM `{kt_schema}`.ent_user
                    WHERE Login = %s
                      AND isGroup = 0
                    LIMIT 1
                """
                logger.debug(f"Looking up KT UserID for login: {kt_login}")
                cursor.execute(sql, (kt_login,))
                row = cursor.fetchone()
                
                if row:
                    user_id = row['UserID']
                    logger.info(f"Found KT UserID {user_id} for login {kt_login}")
                    return user_id
                else:
                    logger.warning(f"No KT UserID found for login {kt_login}")
                    return None
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error looking up KT UserID for login {kt_login}: {str(e)}", exc_info=True)
        return None


def get_user_groups_from_kt_db(kt_user_id: int) -> List[Dict[str, Any]]:
    """
    Query KnowledgeTree database (portal_test2 schema) to get user's groups.
    Uses direct database connection with SSH tunnel support.
    
    Args:
        kt_user_id: KnowledgeTree UserID
        
    Returns:
        List of dicts with: group_id, group_name, group_login
    """
    if not kt_user_id:
        logger.warning("get_user_groups_from_kt_db called with invalid kt_user_id")
        return []
    
    try:
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database: {message}")
            return []
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
            
            logger.debug(f"Querying groups for KT UserID {kt_user_id} from schema {kt_schema}")
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = f"""
                    SELECT
                        uu.ParentUserID as group_id,
                        u.Name as group_name,
                        u.Login as group_login
                    FROM `{kt_schema}`.rel_user_user uu
                    INNER JOIN `{kt_schema}`.ent_user u ON (u.UserID = uu.ParentUserID)
                    WHERE uu.ChildUserID = %s
                      AND u.IsGroup = 1
                    ORDER BY u.Name
                """
                cursor.execute(sql, (kt_user_id,))
                rows = cursor.fetchall()
                
                groups = [
                    {
                        'group_id': row['group_id'],
                        'group_name': row['group_name'] or row['group_login'],
                        'group_login': row['group_login'],
                    }
                    for row in rows
                ]
                
                logger.info(f"Found {len(groups)} groups for KT UserID {kt_user_id}: {[g['group_login'] for g in groups]}")
                return groups
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error querying KnowledgeTree database for UserID {kt_user_id}: {str(e)}", exc_info=True)
        return []


def get_course_ids_from_aggregate_db(group_logins: List[str]) -> Dict[str, List[str]]:
    """
    Query Aggregate database (aggregate schema) to get Course IDs for group logins.
    
    Args:
        group_logins: List of group login strings
        
    Returns:
        Dict mapping group_login to list of course_id strings: {group_login: [course_id1, course_id2, ...]}
    """
    if not group_logins:
        logger.debug("get_course_ids_from_aggregate_db called with empty group_logins list")
        return {}
    
    try:
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database: {message}")
            return {}
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            agg_schema = db_config.get('AGGREGATE_SCHEMA', 'aggregate')
            
            logger.debug(f"Querying Course IDs for {len(group_logins)} groups from schema {agg_schema}")
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Use IN clause for multiple groups
                placeholders = ','.join(['%s'] * len(group_logins))
                sql = f"""
                    SELECT
                        group_id,
                        course_id,
                        group_name
                    FROM `{agg_schema}`.ent_group
                    WHERE group_id IN ({placeholders})
                    ORDER BY group_id, course_id
                """
                cursor.execute(sql, group_logins)
                rows = cursor.fetchall()
                
                # Group by group_login (multiple course_ids possible per group)
                result = {}
                for row in rows:
                    group_login = row['group_id']
                    course_id = str(row['course_id'])  # Convert to string for consistency
                    
                    if group_login not in result:
                        result[group_login] = []
                    result[group_login].append(course_id)
                
                logger.info(f"Found Course IDs for {len(result)} groups from Aggregate database: {dict((k, len(v)) for k, v in result.items())}")
                return result
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error querying Aggregate database: {str(e)}", exc_info=True)
        return {}


def get_user_groups_with_course_ids(user) -> List[Dict[str, Any]]:
    """
    Get user's KnowledgeTree groups with Course IDs using DIRECT database queries.
    
    This function:
    1. Determines the user's KT UserID (from user.kt_user_id or by looking up by kt_login)
    2. Queries KnowledgeTree database for user's groups
    3. Queries Aggregate database for Course IDs associated with those groups
    4. Combines the results
    
    This is MUCH faster than API discovery - uses direct database access.
    No API calls needed!
    
    Args:
        user: Django User object (should have kt_user_id or kt_login set)
        
    Returns:
        List of dicts with: group_id, group_name, group_login, course_ids
    """
    logger.info(f"Getting groups with Course IDs for user {user.username} (kt_user_id={user.kt_user_id}, kt_login={user.kt_login})")
    
    # Step 1: Determine KT UserID
    kt_user_id = user.kt_user_id
    
    # If we don't have kt_user_id but we have kt_login, look it up
    if not kt_user_id and user.kt_login:
        logger.info(f"No kt_user_id for user {user.username}, looking up by kt_login={user.kt_login}")
        kt_user_id = get_kt_user_id_by_login(user.kt_login)
        
        # If we found it, save it to the user object for future use
        if kt_user_id:
            logger.info(f"Found kt_user_id {kt_user_id} for user {user.username}, updating user record")
            user.kt_user_id = kt_user_id
            user.save(update_fields=['kt_user_id'])
        else:
            logger.warning(f"Could not find kt_user_id for user {user.username} with kt_login={user.kt_login}")
            return []
    
    if not kt_user_id:
        logger.warning(f"No kt_user_id available for user {user.username} (kt_login={user.kt_login})")
        return []
    
    # Step 2: Get groups from KnowledgeTree database
    logger.debug(f"Fetching groups for KT UserID {kt_user_id}")
    kt_groups = get_user_groups_from_kt_db(kt_user_id)
    
    if not kt_groups:
        logger.warning(f"No KnowledgeTree groups found for user {user.username} (KT UserID: {kt_user_id})")
        return []
    
    logger.info(f"Found {len(kt_groups)} groups for user {user.username}")
    
    # Step 3: Get Course IDs from Aggregate database
    group_logins = [g['group_login'] for g in kt_groups]
    logger.debug(f"Fetching Course IDs for groups: {group_logins}")
    course_id_mappings = get_course_ids_from_aggregate_db(group_logins)
    
    # Step 4: Combine results
    result = []
    for group in kt_groups:
        group_login = group['group_login']
        course_ids = course_id_mappings.get(group_login, [])
        
        result.append({
            'group_id': group['group_id'],
            'group_name': group['group_name'],
            'group_login': group_login,
            'course_ids': course_ids  # List of Course IDs (usually just one)
        })
        
        logger.debug(f"Group {group_login}: {len(course_ids)} Course IDs found")
    
    logger.info(f"Retrieved {len(result)} groups with Course IDs for user {user.username}")
    return result
