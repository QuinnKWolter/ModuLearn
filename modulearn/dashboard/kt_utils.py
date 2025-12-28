"""
KnowledgeTree utility functions for dashboard integration.
Uses direct database queries for optimal performance.
"""

import logging
import pymysql
from typing import List, Dict, Optional, Any
from django.conf import settings
from .kt_db_connection import get_paws_db_connection
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _get_proxied_url(url: str) -> str:
    """
    Convert HTTP KnowledgeTree URLs to proxied HTTPS URLs for iframe embedding.
    
    Uses the existing proxy system to:
    1. Avoid mixed content errors in production (HTTPS page loading HTTP iframe)
    2. Handle KnowledgeTree's navigation attempts more gracefully
    
    The proxy system in views_proxy.py handles:
    - Converting HTTP to HTTPS via /proxy/http/<host>/<path>
    - Rewriting URLs in HTML content to go through proxy
    - Preserving cookies and session state
    
    Args:
        url: Original HTTP URL (e.g., "http://adapt2.sis.pitt.edu/kt/content/Show?id=6389")
    
    Returns:
        Proxied URL format: /proxy/http/<host>/<path>?<query>
        Or original URL if not HTTP or not in allowed hosts
    """
    u = urlparse(url)
    
    # Only proxy HTTP URLs from allowed hosts
    if u.scheme == "http" and u.hostname in getattr(settings, "PROXY_ALLOWED_HOSTS", set()):
        # Use path-style proxy format: /proxy/http/<host>/<path>?<query>
        # This matches the existing proxy system in views_proxy.py
        path = u.path.lstrip('/')
        base = f"/proxy/http/{u.hostname}/{path}"
        proxied_url = f"{base}?{u.query}" if u.query else base
        logger.debug(f"Proxying KnowledgeTree URL: {url} -> {proxied_url}")
        return proxied_url
    
    # Return original URL if not HTTP or not in allowed hosts
    logger.debug(f"Not proxying URL (not HTTP or not allowed): {url}")
    return url


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
    kt_groups = get_user_groups_from_kt_db(kt_user_id)
    
    if not kt_groups:
        logger.warning(f"No KnowledgeTree groups found for user {user.username} (KT UserID: {kt_user_id})")
        return []
    
    logger.info(f"Found {len(kt_groups)} groups for user {user.username}")
    
    # Step 3: Get Course IDs from Aggregate database
    group_logins = [g['group_login'] for g in kt_groups]
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
        
    
    logger.info(f"Retrieved {len(result)} groups with Course IDs for user {user.username}")
    return result


def get_masterygrids_node_ids_batch(group_logins: List[str], user_kt_user_id: Optional[int] = None) -> Dict[str, Optional[int]]:
    """
    Find MasteryGrids node IDs for multiple groups in a single database query.
    
    This function tries multiple strategies:
    1. Find nodes directly linked to each group (most specific)
    2. Find nodes accessible to the user (if user_kt_user_id provided)
    3. Find any MasteryGrids node that might work (fallback)
    
    This is much more efficient than querying one group at a time, especially
    when SSH tunneling is involved.
    
    Args:
        group_logins: List of group login strings (e.g., ["CMPINF0401Fall2024", ...])
        user_kt_user_id: Optional KnowledgeTree user ID to find user-accessible nodes
        
    Returns:
        Dict mapping group_login to node_id: {group_login: node_id or None}
    """
    if not group_logins:
        return {}
    
    result = {}
    
    try:
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database to find MasteryGrids nodes: {message}")
            # Return None for all groups
            return {group_login: None for group_login in group_logins}
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
            aggregate_schema = db_config.get('AGGREGATE_SCHEMA', 'aggregate')
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Strategy 1: Find nodes directly linked to groups (most specific)
                placeholders = ','.join(['%s'] * len(group_logins))
                sql = f"""
                    SELECT DISTINCT 
                        u.Login as group_login,
                        n.NodeID,
                        n.Title,
                        n.URL
                    FROM `{kt_schema}`.ent_node n
                    INNER JOIN `{kt_schema}`.ent_right r ON r.NodeID = n.NodeID
                    INNER JOIN `{kt_schema}`.ent_user u ON u.UserID = r.UserID
                    WHERE u.Login IN ({placeholders})
                      AND u.isGroup = 1
                      AND (n.URL LIKE '%%mastery-grids%%' 
                           OR n.URL LIKE '%%masterygrids%%'
                           OR n.Title LIKE '%%Mastery%%Grid%%')
                      AND n.Hidden = 0
                    ORDER BY u.Login, n.NodeID
                """
                cursor.execute(sql, group_logins)
                rows = cursor.fetchall()
                
                # Initialize all groups with None
                result = {group_login: None for group_login in group_logins}
                
                # Map results from Strategy 1
                for row in rows:
                    group_login = row['group_login']
                    node_id = row['NodeID']
                    # If multiple nodes found for same group, use the first one
                    if result[group_login] is None:
                        result[group_login] = node_id
                        logger.debug(f"Found MasteryGrids node ID {node_id} for group {group_login} (direct link)")
                
                # Strategy 2: For groups without nodes, try to find user-accessible nodes
                if user_kt_user_id:
                    groups_without_nodes = [gl for gl, node_id in result.items() if node_id is None]
                    if groups_without_nodes:
                        # Find MasteryGrids nodes accessible to the user
                        user_sql = f"""
                            SELECT DISTINCT 
                                n.NodeID,
                                n.Title,
                                n.URL
                            FROM `{kt_schema}`.ent_node n
                            INNER JOIN `{kt_schema}`.ent_right r ON r.NodeID = n.NodeID
                            WHERE r.UserID = %s
                              AND (n.URL LIKE '%%mastery-grids%%' 
                                   OR n.URL LIKE '%%masterygrids%%'
                                   OR n.Title LIKE '%%Mastery%%Grid%%')
                              AND n.Hidden = 0
                            ORDER BY n.NodeID
                            LIMIT 1
                        """
                        cursor.execute(user_sql, [user_kt_user_id])
                        user_node = cursor.fetchone()
                        if user_node:
                            # Use this node for all groups that don't have their own
                            shared_node_id = user_node['NodeID']
                            for group_login in groups_without_nodes:
                                if result[group_login] is None:
                                    result[group_login] = shared_node_id
                                    logger.debug(f"Using user-accessible MasteryGrids node ID {shared_node_id} for group {group_login}")
                
                # Strategy 3: For remaining groups, try to find any MasteryGrids node
                groups_still_without = [gl for gl, node_id in result.items() if node_id is None]
                if groups_still_without:
                    # Find any MasteryGrids node (might be a shared/global one)
                    global_sql = f"""
                        SELECT DISTINCT 
                            n.NodeID,
                            n.Title,
                            n.URL
                        FROM `{kt_schema}`.ent_node n
                        WHERE (n.URL LIKE '%%mastery-grids%%' 
                               OR n.URL LIKE '%%masterygrids%%'
                               OR n.Title LIKE '%%Mastery%%Grid%%')
                          AND n.Hidden = 0
                        ORDER BY n.NodeID
                        LIMIT 1
                    """
                    cursor.execute(global_sql)
                    global_node = cursor.fetchone()
                    if global_node:
                        # Use this node for all remaining groups (might work, might not)
                        fallback_node_id = global_node['NodeID']
                        for group_login in groups_still_without:
                            if result[group_login] is None:
                                result[group_login] = fallback_node_id
                                logger.debug(f"Using fallback MasteryGrids node ID {fallback_node_id} for group {group_login}")
                
                found_count = sum(1 for v in result.values() if v is not None)
                logger.info(f"Found MasteryGrids node IDs for {found_count}/{len(group_logins)} groups in batch query")
                
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error finding MasteryGrids node IDs in batch: {str(e)}", exc_info=True)
        # Return None for all groups on error
        return {group_login: None for group_login in group_logins}
    
    return result


def get_user_groups_with_masterygrids_nodes(user) -> List[Dict[str, Any]]:
    """
    Get user's KnowledgeTree groups with Course IDs and MasteryGrids node IDs.
    
    This is an enhanced version of get_user_groups_with_course_ids that also
    includes MasteryGrids node IDs for each group. Uses batch querying for efficiency.
    Tries multiple strategies to find MasteryGrids nodes for all groups.
    
    Args:
        user: Django User object (should have kt_user_id or kt_login set)
        
    Returns:
        List of dicts with: group_id, group_name, group_login, course_ids, masterygrids_node_id
    """
    # First get groups with course IDs
    groups = get_user_groups_with_course_ids(user)
    
    if not groups:
        return groups
    
    # Get user's KT user ID for finding user-accessible nodes
    kt_user_id = getattr(user, 'kt_user_id', None)
    if not kt_user_id and hasattr(user, 'kt_login') and user.kt_login:
        # Try to look up kt_user_id if not set
        try:
            kt_user_id = get_kt_user_id_by_login(user.kt_login)
        except Exception as e:
            logger.debug(f"Could not look up kt_user_id for {user.kt_login}: {str(e)}")
            kt_user_id = None
    
    # Batch query all MasteryGrids node IDs at once (much more efficient)
    group_logins = [group['group_login'] for group in groups]
    node_id_mappings = get_masterygrids_node_ids_batch(group_logins, user_kt_user_id=kt_user_id)
    
    # Add MasteryGrids node IDs to groups
    for group in groups:
        group_login = group['group_login']
        group['masterygrids_node_id'] = node_id_mappings.get(group_login)
    
    found_count = sum(1 for g in groups if g.get('masterygrids_node_id') is not None)
    logger.info(f"Retrieved {len(groups)} groups with MasteryGrids node IDs ({found_count} found) for user {user.username}")
    return groups


def get_course_resources(group_login: str) -> List[Dict[str, Any]]:
    """
    Get all course resources for a KnowledgeTree group.
    
    This function finds the course container node (folder child of root "Folders" node)
    and returns all resources (children of the course container).
    
    Args:
        group_login: Group login string (e.g., "CS0007Fall20242")
    
    Returns:
        List of resource dictionaries with NodeID, Title, URL, show_url, resource_type, etc.
    """
    if not group_login:
        logger.warning("get_course_resources called with empty group_login")
        return []
    
    logger.info(f"Getting course resources for group: {group_login}")
    
    try:
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database to get course resources: {message}")
            return []
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
            
            logger.debug(f"Using schema: {kt_schema} for group: {group_login}")
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Step 1: Verify group exists and get Group UserID
                group_check_sql = f"""
                    SELECT UserID, Name, Login, isGroup
                    FROM `{kt_schema}`.ent_user
                    WHERE Login = %s AND isGroup = 1
                    LIMIT 1
                """
                cursor.execute(group_check_sql, [group_login])
                group_info = cursor.fetchone()
                
                if not group_info:
                    logger.warning(f"Group '{group_login}' not found or is not a group (isGroup=1)")
                    return []
                
                group_user_id = group_info['UserID']
                logger.info(f"Found group: {group_login} (UserID: {group_user_id}, Name: {group_info.get('Name', 'N/A')})")
                
                # Step 2: Find course container node (folder child of root "Folders" node)
                container_sql = f"""
                    SELECT 
                        n.NodeID,
                        n.Title,
                        n.FolderFlag,
                        rnn.ParentNodeID,
                        rnn.OrderRank
                    FROM `{kt_schema}`.ent_node n
                    INNER JOIN `{kt_schema}`.rel_node_node rnn ON rnn.ChildNodeID = n.NodeID
                    INNER JOIN `{kt_schema}`.ent_right r ON r.NodeID = n.NodeID
                    INNER JOIN `{kt_schema}`.ent_user u ON u.UserID = r.UserID
                    WHERE u.Login = %s
                      AND u.isGroup = 1
                      AND n.FolderFlag = 1
                      AND rnn.ParentNodeID = 1
                    ORDER BY rnn.OrderRank
                    LIMIT 1
                """
                logger.debug(f"Querying for course container node (ParentNodeID=1, FolderFlag=1) for group: {group_login}")
                cursor.execute(container_sql, [group_login])
                container_result = cursor.fetchone()
                
                if not container_result:
                    logger.warning(f"No course container node found for group {group_login} (folder with ParentNodeID=1)")
                    
                    # Try alternative: Find any folder nodes accessible to this group
                    alt_container_sql = f"""
                        SELECT 
                            n.NodeID,
                            n.Title,
                            n.FolderFlag,
                            rnn.ParentNodeID,
                            rnn.OrderRank
                        FROM `{kt_schema}`.ent_node n
                        INNER JOIN `{kt_schema}`.rel_node_node rnn ON rnn.ChildNodeID = n.NodeID
                        INNER JOIN `{kt_schema}`.ent_right r ON r.NodeID = n.NodeID
                        WHERE r.UserID = %s
                          AND n.FolderFlag = 1
                        ORDER BY rnn.ParentNodeID, rnn.OrderRank
                        LIMIT 5
                    """
                    logger.debug(f"Trying alternative query: any folder nodes accessible to group UserID {group_user_id}")
                    cursor.execute(alt_container_sql, [group_user_id])
                    alt_results = cursor.fetchall()
                    
                    if alt_results:
                        logger.info(f"Found {len(alt_results)} alternative folder nodes for group {group_login}:")
                        for alt in alt_results:
                            logger.info(f"  - NodeID: {alt['NodeID']}, Title: {alt['Title']}, ParentNodeID: {alt['ParentNodeID']}")
                    else:
                        logger.warning(f"No folder nodes found at all for group {group_login}")
                    
                    return []
                
                container_node_id = container_result['NodeID']
                container_title = container_result.get('Title', 'N/A')
                logger.info(f"Found course container: NodeID={container_node_id}, Title='{container_title}' for group {group_login}")
                
                # Step 3: Verify group has access to container node
                container_access_sql = f"""
                    SELECT COUNT(*) as access_count
                    FROM `{kt_schema}`.ent_right r
                    INNER JOIN `{kt_schema}`.ent_user u ON u.UserID = r.UserID
                    WHERE r.NodeID = %s
                      AND u.Login = %s
                      AND u.isGroup = 1
                """
                cursor.execute(container_access_sql, [container_node_id, group_login])
                container_access = cursor.fetchone()
                has_container_access = container_access['access_count'] > 0 if container_access else False
                logger.info(f"Group {group_login} has direct access to container NodeID={container_node_id}: {has_container_access}")
                
                # Step 4: Get course resources (children of course container)
                # Since permissions may be inherited from parent, we'll try two approaches:
                # 1. First try with direct ent_right entries (original approach)
                # 2. If that fails, get all children and verify container access (inherited permissions)
                
                resources_sql_direct = f"""
                    SELECT 
                        n.NodeID,
                        n.Title,
                        n.FolderFlag,
                        n.URL,
                        n.ItemTypeID,
                        COALESCE(rnn.OrderRank, 999) as OrderRank,
                        n.Hidden,
                        n.Description
                    FROM `{kt_schema}`.ent_node n
                    INNER JOIN `{kt_schema}`.rel_node_node rnn ON rnn.ChildNodeID = n.NodeID
                    INNER JOIN `{kt_schema}`.ent_right r ON r.NodeID = n.NodeID
                    INNER JOIN `{kt_schema}`.ent_user u ON u.UserID = r.UserID
                    WHERE rnn.ParentNodeID = %s
                      AND u.Login = %s
                      AND u.isGroup = 1
                      AND n.Hidden = 0
                    ORDER BY rnn.OrderRank ASC, n.Title ASC
                """
                logger.debug(f"Querying for resources with direct ent_right entries (children of container NodeID={container_node_id}) for group: {group_login}")
                cursor.execute(resources_sql_direct, [container_node_id, group_login])
                rows = cursor.fetchall()
                
                logger.info(f"Direct ent_right query returned {len(rows)} rows for group {group_login}")
                
                # If no direct entries found, try inherited permissions approach
                if len(rows) == 0 and has_container_access:
                    logger.info(f"No direct ent_right entries found for child nodes. Trying inherited permissions approach...")
                    resources_sql_inherited = f"""
                        SELECT 
                            n.NodeID,
                            n.Title,
                            n.FolderFlag,
                            n.URL,
                            n.ItemTypeID,
                            COALESCE(rnn.OrderRank, 999) as OrderRank,
                            n.Hidden,
                            n.Description
                        FROM `{kt_schema}`.ent_node n
                        INNER JOIN `{kt_schema}`.rel_node_node rnn ON rnn.ChildNodeID = n.NodeID
                        WHERE rnn.ParentNodeID = %s
                          AND n.Hidden = 0
                        ORDER BY rnn.OrderRank ASC, n.Title ASC
                    """
                    logger.debug(f"Querying for all children of container NodeID={container_node_id} (assuming inherited permissions)")
                    cursor.execute(resources_sql_inherited, [container_node_id])
                    rows = cursor.fetchall()
                    
                    if rows:
                        logger.info(f"Inherited permissions query returned {len(rows)} rows (group has access to container, so children are accessible)")
                    else:
                        logger.warning(f"No children found at all for container NodeID={container_node_id}")
                elif len(rows) == 0:
                    # Try query without group login filter to see if there are any children at all
                    alt_resources_sql = f"""
                        SELECT 
                            n.NodeID,
                            n.Title,
                            n.FolderFlag,
                            n.URL,
                            n.Hidden,
                            rnn.ParentNodeID
                        FROM `{kt_schema}`.ent_node n
                        INNER JOIN `{kt_schema}`.rel_node_node rnn ON rnn.ChildNodeID = n.NodeID
                        WHERE rnn.ParentNodeID = %s
                          AND n.Hidden = 0
                        ORDER BY rnn.OrderRank ASC
                        LIMIT 10
                    """
                    logger.debug(f"Trying alternative query: all children of container NodeID={container_node_id} (without group filter)")
                    cursor.execute(alt_resources_sql, [container_node_id])
                    alt_rows = cursor.fetchall()
                    
                    if alt_rows:
                        logger.warning(f"Found {len(alt_rows)} children of container NodeID={container_node_id}, but group '{group_login}' has no access to container")
                        logger.info(f"Sample children (first 3):")
                        for alt in alt_rows[:3]:
                            logger.info(f"  - NodeID: {alt['NodeID']}, Title: {alt['Title']}, Hidden: {alt['Hidden']}")
                        
                        # Check what groups have access to these nodes
                        if alt_rows:
                            sample_node_id = alt_rows[0]['NodeID']
                            access_check_sql = f"""
                                SELECT DISTINCT u.Login, u.isGroup, u.Name
                                FROM `{kt_schema}`.ent_right r
                                INNER JOIN `{kt_schema}`.ent_user u ON u.UserID = r.UserID
                                WHERE r.NodeID = %s
                                LIMIT 5
                            """
                            cursor.execute(access_check_sql, [sample_node_id])
                            access_groups = cursor.fetchall()
                            logger.info(f"Groups with access to sample node {sample_node_id}: {[g['Login'] for g in access_groups]}")
                    else:
                        logger.warning(f"No children found at all for container NodeID={container_node_id}")
                
                resources = []
                for row in rows:
                    resource = dict(row)
                    # Construct Show servlet URL for IFrame rendering
                    # Use proxy in production (HTTPS) to avoid mixed content issues
                    original_url = f"http://adapt2.sis.pitt.edu/kt/content/Show?id={resource['NodeID']}"
                    resource['show_url'] = _get_proxied_url(original_url)
                    resource['show_url_direct'] = original_url  # Keep original for fallback
                    # Determine resource type
                    url_lower = (resource.get('URL') or '').lower()
                    if 'mastery-grids' in url_lower or 'masterygrids' in url_lower:
                        resource['resource_type'] = 'masterygrids'
                    elif resource.get('FolderFlag', 0) == 1:
                        resource['resource_type'] = 'folder'
                    else:
                        resource['resource_type'] = 'resource'
                    resources.append(resource)
                
                if resources:
                    logger.info(f"Successfully found {len(resources)} course resources for group {group_login}")
                    logger.debug(f"Resource types: {[r['resource_type'] for r in resources[:5]]}")
                    logger.debug(f"Sample resources (first 3): {[{'NodeID': r['NodeID'], 'Title': r['Title'], 'Type': r['resource_type']} for r in resources[:3]]}")
                else:
                    logger.warning(f"Found 0 course resources for group {group_login} (container NodeID={container_node_id})")
                
                return resources
                
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error getting course resources for group {group_login}: {str(e)}", exc_info=True)
        return []
