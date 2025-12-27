"""
Direct database queries to replace GetClassList and GetContentLevels API calls.
Uses direct database access for optimal performance.
"""

import logging
import pymysql
import re
from typing import List, Dict, Optional, Any
from django.conf import settings
from .kt_db_connection import get_paws_db_connection

logger = logging.getLogger(__name__)


def get_class_list_from_db(group_login: str) -> Dict[str, Any]:
    """
    Get all students in a group from KnowledgeTree database.
    Replaces GetClassList API call.
    
    Args:
        group_login: KnowledgeTree group login (e.g., "IS172013Fall")
        
    Returns:
        Dict with 'learners' array and 'groupName'
    """
    try:
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database: {message}")
            return {'learners': [], 'groupName': group_login}
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            kt_schema = db_config.get('KNOWLEDGETREE_SCHEMA', 'portal_test2')
            agg_schema = db_config.get('AGGREGATE_SCHEMA', 'aggregate')
            
            logger.info(f"Fetching class list for group: {group_login}")
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get group info and students from KnowledgeTree
                sql = f"""
                    SELECT DISTINCT
                        u.UserID as user_id,
                        u.Login as learner_id,
                        u.Name as name,
                        u.EMail as email,
                        g.UserID as group_id,
                        g.Name as group_name,
                        g.Login as group_login
                    FROM `{kt_schema}`.rel_user_user uu
                    INNER JOIN `{kt_schema}`.ent_user u ON u.UserID = uu.ChildUserID
                    INNER JOIN `{kt_schema}`.ent_user g ON g.UserID = uu.ParentUserID
                    WHERE g.Login = %s
                      AND u.isGroup = 0
                      AND g.isGroup = 1
                    ORDER BY u.Name
                """
                cursor.execute(sql, (group_login,))
                students = cursor.fetchall()
                
                if not students:
                    logger.warning(f"No students found for group: {group_login}")
                    return {'learners': [], 'groupName': group_login}
                
                # Get non-students to exclude from analytics
                non_students = set()
                try:
                    non_students_sql = f"""
                        SELECT user_id
                        FROM `{agg_schema}`.ent_non_student
                        WHERE group_id = %s
                    """
                    cursor.execute(non_students_sql, (group_login,))
                    non_student_rows = cursor.fetchall()
                    non_students = {row['user_id'] for row in non_student_rows}
                except Exception as e:
                    logger.warning(f"Could not fetch non-students list: {str(e)}")
                
                # Filter out non-students and format response
                learners = []
                group_name = students[0]['group_name'] if students else group_login
                
                for student in students:
                    # Exclude if in non-students list (check both user_id and learner_id)
                    if student['user_id'] in non_students or student['learner_id'] in non_students:
                        continue
                    
                    learners.append({
                        'learnerId': student['learner_id'],
                        'name': student['name'] or student['learner_id'],
                        'email': student['email'] or ''
                    })
                
                logger.info(f"Found {len(learners)} students for group {group_login}")
                return {
                    'learners': learners,
                    'groupName': group_name
                }
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error fetching class list from database: {str(e)}", exc_info=True)
        return {'learners': [], 'groupName': group_login}


def get_course_structure_from_db(group_login: str, course_id: int) -> Dict[str, Any]:
    """
    Get complete course structure from aggregate database.
    Replaces GetContentLevels API call for course structure (topics, resources, content).
    
    Args:
        group_login: KnowledgeTree group login
        course_id: Course ID (integer)
        
    Returns:
        Dict with course structure: topics, resources, content mappings
    """
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
            
            logger.info(f"Fetching course structure for group: {group_login}, course_id: {course_id}")
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Get course basic info
                course_sql = f"""
                    SELECT 
                        G.course_id,
                        G.group_name,
                        G.group_id,
                        C.course_name,
                        C.course_code,
                        C.domain,
                        C.desc as course_description
                    FROM `{agg_schema}`.ent_group G
                    INNER JOIN `{agg_schema}`.ent_course C ON C.course_id = G.course_id
                    WHERE G.group_id = %s AND G.course_id = %s
                    LIMIT 1
                """
                cursor.execute(course_sql, (group_login, course_id))
                course_info = cursor.fetchone()
                
                if not course_info:
                    logger.warning(f"Course not found: group={group_login}, course_id={course_id}")
                    return {}
                
                # Get topics
                topics_sql = f"""
                    SELECT 
                        T.topic_id,
                        T.topic_name,
                        T.display_name,
                        T.`order`,
                        T.visible,
                        T.desc as topic_description,
                        T.parent,
                        T.domain
                    FROM `{agg_schema}`.ent_topic T
                    WHERE T.course_id = %s
                      AND T.active = 1
                    ORDER BY T.`order` ASC
                """
                cursor.execute(topics_sql, (course_id,))
                topic_rows = cursor.fetchall()
                
                # Get hidden topics for this group
                hidden_topics_sql = f"""
                    SELECT topic_name
                    FROM `{agg_schema}`.ent_hidden_topics
                    WHERE group_id = %s
                """
                cursor.execute(hidden_topics_sql, (group_login,))
                hidden_topic_rows = cursor.fetchall()
                hidden_topics = {row['topic_name'] for row in hidden_topic_rows}
                
                # Get resources
                resources_sql = f"""
                    SELECT 
                        R.resource_id,
                        R.resource_name,
                        R.display_name,
                        R.`desc` as resource_description,
                        R.visible,
                        R.update_state_on,
                        R.`order`,
                        R.window_width,
                        R.window_height
                    FROM `{agg_schema}`.ent_resource R
                    WHERE R.course_id = %s
                    ORDER BY R.`order`
                """
                cursor.execute(resources_sql, (course_id,))
                resource_rows = cursor.fetchall()
                
                # Get content organized by topic and resource
                content_sql = f"""
                    SELECT 
                        T.topic_name,
                        T.display_name as topic_display_name,
                        T.`order` as topic_order,
                        R.resource_name,
                        R.display_name as resource_display_name,
                        R.`order` as resource_order,
                        C.content_name,
                        C.display_name as content_display_name,
                        C.url,
                        C.provider_id,
                        TC.display_order
                    FROM `{agg_schema}`.ent_topic T
                    INNER JOIN `{agg_schema}`.rel_topic_content TC ON TC.topic_id = T.topic_id
                    INNER JOIN `{agg_schema}`.ent_content C ON C.content_id = TC.content_id
                    INNER JOIN `{agg_schema}`.ent_resource R ON R.resource_id = TC.resource_id
                    WHERE T.course_id = %s
                      AND T.active = 1
                      AND C.visible = 1
                      AND TC.visible = 1
                    ORDER BY T.`order`, R.`order` DESC, TC.display_order ASC
                """
                cursor.execute(content_sql, (course_id,))
                content_rows = cursor.fetchall()
                
                # Organize topics with activities
                topics = []
                topic_map = {}
                
                for topic_row in topic_rows:
                    topic_name = topic_row['topic_name']
                    
                    # Skip hidden topics
                    if topic_name in hidden_topics:
                        continue
                    
                    topic = {
                        'id': topic_name,
                        'name': topic_row['display_name'] or topic_name,
                        'order': topic_row['order'],
                        'activities': {}
                    }
                    topics.append(topic)
                    topic_map[topic_name] = topic
                
                # Organize content by topic and resource
                for content_row in content_rows:
                    topic_name = content_row['topic_name']
                    resource_name = content_row['resource_name']
                    
                    # Skip if topic is hidden
                    if topic_name in hidden_topics or topic_name not in topic_map:
                        continue
                    
                    topic = topic_map[topic_name]
                    
                    # Initialize resource activities array if needed
                    if resource_name not in topic['activities']:
                        topic['activities'][resource_name] = []
                    
                    # Add content item to activities
                    topic['activities'][resource_name].append({
                        'id': content_row['content_name'],
                        'name': content_row['content_display_name'] or content_row['content_name'],
                        'url': content_row['url'] or ''
                    })
                
                # Build resources list
                resources = [
                    {
                        'id': row['resource_name'],
                        'name': row['display_name'] or row['resource_name']
                    }
                    for row in resource_rows
                ]
                
                logger.info(f"Found {len(topics)} topics, {len(resources)} resources for course {course_id}")
                
                return {
                    'course_id': course_id,
                    'course_name': course_info['course_name'],
                    'group_name': course_info['group_name'],
                    'domain': course_info['domain'],
                    'topics': topics,
                    'resources': resources
                }
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error fetching course structure from database: {str(e)}", exc_info=True)
        return {}


def parse_computed_model(model_string: str, is_topics: bool = True, resource_names: List[str] = None) -> Dict[str, Any]:
    """
    Parse pipe-delimited model data from ent_computed_models.
    
    Format:
    - Topics: "topic_name:value1,value2,...,value10|topic_name:..."
    - Content: "content_name:value1,value2,...|content_name:..."
    
    For topics: Each entry is `topic_name:value1,value2,...,value10`
    - 10 values total = 5 resources × 2 values per resource (k, p)
    - Values are paired: (k1, p1, k2, p2, k3, p3, k4, p4, k5, p5)
    
    For content: Similar format but may have different number of values
    
    Args:
        model_string: Pipe-delimited string from model4topics or model4content
        is_topics: True for model4topics, False for model4content
        resource_names: List of resource names in order (to map values to resources)
        
    Returns:
        For topics: Dict structure: {topic_name: {resource_name: {k: float, p: float}}}
        For content: Dict structure: {content_name: {k: float, p: float}}
    """
    if not model_string:
        return {}
    
    result = {}
    parts = model_string.split('|')
    
    # Parse format: name:value1,value2,value3,...
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Split on first colon to get name and values
        if ':' not in part:
            continue
        
        name, values_str = part.split(':', 1)
        name = name.strip()
        
        # Parse comma-separated values
        try:
            values = [v.strip() for v in values_str.split(',')]
            
            if is_topics:
                # For topics: values are paired (k, p) for each resource
                # Format: k1, p1, k2, p2, k3, p3, ... (2 values per resource)
                # Number of resources = len(values) / 2
                num_pairs = len(values) // 2
                
                if num_pairs > 0:
                    if name not in result:
                        result[name] = {'values': {}, 'overall': {'k': 0.0, 'p': 0.0}}
                    
                    # Map to resources if provided, otherwise use generic names
                    for i in range(num_pairs):
                        if resource_names and i < len(resource_names):
                            resource_name = resource_names[i]
                        else:
                            resource_name = f'resource_{i+1}'
                        
                        try:
                            k = float(values[i * 2]) if i * 2 < len(values) else 0.0
                            p = float(values[i * 2 + 1]) if i * 2 + 1 < len(values) else 0.0
                            result[name]['values'][resource_name] = {'k': k, 'p': p}
                        except (ValueError, IndexError):
                            result[name]['values'][resource_name] = {'k': 0.0, 'p': 0.0}
            else:
                # For content: Activity-level progress data
                # Format: content_name:value1,value2,value3,...
                # The first two values are k (knowledge) and p (progress)
                # Store as dict: {content_name: {k: float, p: float}}
                if len(values) >= 2:
                    try:
                        k = float(values[0]) if values[0] else 0.0
                        p = float(values[1]) if values[1] else 0.0
                        # Store by content_name (activity ID)
                        result[name] = {'k': k, 'p': p}
                    except (ValueError, IndexError):
                        result[name] = {'k': 0.0, 'p': 0.0}
                
        except (ValueError, IndexError) as e:
            # Skip this entry if parsing fails
            continue
    
    # Calculate overall for each topic (only for topics, not content)
    if is_topics:
        for topic_name, topic_data in result.items():
            if topic_data.get('values'):
                values = list(topic_data['values'].values())
                avg_k = sum(v['k'] for v in values) / len(values)
                avg_p = sum(v['p'] for v in values) / len(values)
                topic_data['overall'] = {'k': avg_k, 'p': avg_p}
    
    return result


def fetch_all_students_analytics(group_login: str, course_id: int) -> Dict[str, Any]:
    """
    Fetch analytics data for ALL students in a course in a single batch operation.
    This is much more efficient than fetching students one-by-one.
    
    Args:
        group_login: KnowledgeTree group login
        course_id: Course ID
        
    Returns:
        Complete analytics response with all students' data
    """
    try:
        logger.info(f"Batch fetching analytics for group: {group_login}, course: {course_id}")
        
        # Step 1: Get class list
        class_list_data = get_class_list_from_db(group_login)
        if not class_list_data or not class_list_data.get('learners'):
            logger.warning(f"No students found for group: {group_login}")
            return {
                'learners': [],
                'topics': [],
                'resources': [],
                'groups': [],
                'context': {}
            }
        
        learner_ids = [l['learnerId'] for l in class_list_data['learners']]
        logger.info(f"Found {len(learner_ids)} students")
        
        # Step 2: Get course structure (once for all students)
        course_structure = get_course_structure_from_db(group_login, course_id)
        if not course_structure:
            logger.warning(f"Course structure not found for group: {group_login}, course: {course_id}")
            return {
                'learners': [],
                'topics': [],
                'resources': [],
                'groups': [],
                'context': {}
            }
        
        topics = course_structure.get('topics', [])
        resources = course_structure.get('resources', [])
        
        # Step 3: Batch fetch all students' progress
        # Extract resource names in order for proper mapping
        resource_names = [r['id'] for r in resources] if resources else None
        logger.info(f"Batch fetching progress for {len(learner_ids)} students")
        all_progress = get_all_students_progress_from_db(learner_ids, course_id, resource_names=resource_names)
        logger.info(f"Retrieved progress data for {len(all_progress)} students")
        
        # Step 4: Build learners array with progress data
        learners = []
        learner_map = {learner['learnerId']: learner for learner in class_list_data.get('learners', [])}
        
        for learner_id in learner_ids:
            learner_info = learner_map.get(learner_id, {
                'learnerId': learner_id,
                'name': learner_id,
                'email': ''
            })
            
            progress_data = all_progress.get(learner_id, {})
            topics_data = progress_data.get('topics', {})
            content_data = progress_data.get('content', {})
            
            # Build state structure
            state = {
                'topics': {},
                'activities': {}
            }
            
            # Populate topics data
            for topic in topics:
                topic_name = topic['id']
                topic_progress = topics_data.get(topic_name, {})
                
                state['topics'][topic_name] = {
                    'values': {},
                    'overall': topic_progress.get('overall', {'k': 0.0, 'p': 0.0})
                }
                
                # Populate resource values
                for resource in resources:
                    resource_name = resource['id']
                    resource_values = topic_progress.get('values', {}).get(resource_name, {'k': 0.0, 'p': 0.0})
                    state['topics'][topic_name]['values'][resource_name] = resource_values
                
                # Build activities structure with progress data
                state['activities'][topic_name] = {}
                for resource_name, activities in topic.get('activities', {}).items():
                    # Convert array to object keyed by activity ID, including progress
                    activities_obj = {}
                    for activity in activities:
                        activity_id = activity['id']
                        activity_progress = content_data.get(activity_id, {'k': 0.0, 'p': 0.0})
                        
                        activities_obj[activity_id] = {
                            'id': activity_id,
                            'name': activity['name'],
                            'url': activity.get('url', ''),
                            'values': {
                                'k': activity_progress.get('k', 0.0),
                                'p': activity_progress.get('p', 0.0)
                            }
                        }
                    state['activities'][topic_name][resource_name] = activities_obj
            
            learners.append({
                'id': learner_id,
                'name': learner_info.get('name', learner_id),
                'email': learner_info.get('email', ''),
                'isHidden': False,
                'state': state
            })
        
        # Step 5: Build context
        context = {
            'group': {
                'name': class_list_data.get('groupName', group_login)
            },
            'learnerId': None,
            'course_id': course_id,
            'course_name': course_structure.get('course_name', ''),
            'domain': course_structure.get('domain', '')
        }
        
        # Step 6: Build class average
        class_average_state = {
            'topics': {}
        }
        
        # Calculate class averages
        for topic in topics:
            topic_name = topic['id']
            class_average_state['topics'][topic_name] = {
                'values': {},
                'overall': {'k': 0.0, 'p': 0.0}
            }
            
            # Calculate average for each resource
            for resource in resources:
                resource_name = resource['id']
                total_progress = 0.0
                count = 0
                
                for learner in learners:
                    topic_data = learner['state']['topics'].get(topic_name, {})
                    resource_data = topic_data.get('values', {}).get(resource_name, {})
                    if resource_data and 'p' in resource_data:
                        total_progress += resource_data['p']
                        count += 1
                
                avg_progress = total_progress / count if count > 0 else 0.0
                class_average_state['topics'][topic_name]['values'][resource_name] = {
                    'k': 0.0,
                    'p': avg_progress
                }
            
            # Calculate overall topic progress
            resource_values = list(class_average_state['topics'][topic_name]['values'].values())
            avg_topic_progress = sum(v['p'] for v in resource_values) / len(resource_values) if resource_values else 0.0
            class_average_state['topics'][topic_name]['overall'] = {
                'k': 0.0,
                'p': avg_topic_progress
            }
        
        logger.info(f"Successfully built analytics response for {len(learners)} students")
        
        return {
            'learners': learners,
            'topics': topics,
            'resources': resources,
            'groups': [
                {
                    'name': 'Class Average',
                    'state': class_average_state
                }
            ],
            'context': context
        }
    except Exception as e:
        logger.error(f"Error in fetch_all_students_analytics: {str(e)}", exc_info=True)
        return {
            'learners': [],
            'topics': [],
            'resources': [],
            'groups': [],
            'context': {}
        }


def get_student_progress_from_db(learner_id: str, course_id: int) -> Optional[Dict[str, Any]]:
    """
    Get individual student progress from ent_computed_models.
    
    Args:
        learner_id: Student username/login
        course_id: Course ID
        
    Returns:
        Dict with parsed model data or None if not found
    """
    try:
        db_conn = get_paws_db_connection()
        success, message = db_conn.connect()
        
        if not success:
            logger.error(f"Failed to connect to PAWS database: {message}")
            return None
        
        try:
            connection = db_conn.get_connection()
            db_config = getattr(settings, 'PAWS_DATABASE', {})
            agg_schema = db_config.get('AGGREGATE_SCHEMA', 'aggregate')
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                sql = f"""
                    SELECT 
                        user_id,
                        course_id,
                        model4topics,
                        model4content,
                        model4kc,
                        last_update
                    FROM `{agg_schema}`.ent_computed_models
                    WHERE user_id = %s
                      AND course_id = %s
                    ORDER BY last_update DESC
                    LIMIT 1
                """
                cursor.execute(sql, (learner_id, course_id))
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                # Parse model data
                topics_data = parse_computed_model(row['model4topics'] or '', is_topics=True, resource_names=resource_names)
                content_data = parse_computed_model(row['model4content'] or '', is_topics=False, resource_names=resource_names)
                
                return {
                    'topics': topics_data,
                    'content': content_data,
                    'last_update': row['last_update'].isoformat() if row['last_update'] else None
                }
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error fetching student progress from database: {str(e)}", exc_info=True)
        return None


def build_analytics_response(group_login: str, course_id: int, learner_ids: List[str], 
                             class_list_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build complete analytics response structure matching GetContentLevels format.
    Combines course structure, student progress, and organizes data for frontend.
    
    Args:
        group_login: KnowledgeTree group login
        course_id: Course ID
        learner_ids: List of student usernames/logins
        class_list_data: Class list data from get_class_list_from_db
        
    Returns:
        Complete analytics response matching GetContentLevels format
    """
    try:
        # Get course structure
        course_structure = get_course_structure_from_db(group_login, course_id)
        if not course_structure:
            logger.error(f"Could not fetch course structure for group {group_login}, course {course_id}")
            return {}
        
        topics = course_structure.get('topics', [])
        resources = course_structure.get('resources', [])
        
        # Batch fetch all students' progress
        all_progress = get_all_students_progress_from_db(learner_ids, course_id)
        
        # Build learners array with progress data
        learners = []
        learner_map = {learner['learnerId']: learner for learner in class_list_data.get('learners', [])}
        
        for learner_id in learner_ids:
            learner_info = learner_map.get(learner_id, {
                'learnerId': learner_id,
                'name': learner_id,
                'email': ''
            })
            
            progress_data = all_progress.get(learner_id, {})
            topics_data = progress_data.get('topics', {})
            content_data = progress_data.get('content', {})  # Activity-level progress
            
            # Build state structure
            state = {
                'topics': {},
                'activities': {}
            }
            
            # Populate topics data
            for topic in topics:
                topic_name = topic['id']
                topic_progress = topics_data.get(topic_name, {})
                
                state['topics'][topic_name] = {
                    'values': {},
                    'overall': topic_progress.get('overall', {'k': 0.0, 'p': 0.0})
                }
                
                # Populate resource values
                for resource in resources:
                    resource_name = resource['id']
                    resource_values = topic_progress.get('values', {}).get(resource_name, {'k': 0.0, 'p': 0.0})
                    state['topics'][topic_name]['values'][resource_name] = resource_values
                
                # Build activities structure with progress data
                state['activities'][topic_name] = {}
                for resource_name, activities in topic.get('activities', {}).items():
                    state['activities'][topic_name][resource_name] = {
                        activity['id']: {
                            'id': activity['id'],
                            'name': activity['name'],
                            'url': activity.get('url', ''),
                            'values': {
                                'k': content_data.get(activity['id'], {}).get('k', 0.0),
                                'p': content_data.get(activity['id'], {}).get('p', 0.0)
                            }
                        }
                        for activity in activities
                    }
            
            learners.append({
                'id': learner_id,
                'name': learner_info.get('name', learner_id),
                'email': learner_info.get('email', ''),
                'isHidden': False,  # Could be determined from non_students list if needed
                'state': state
            })
        
        # Build context
        context = {
            'group': {
                'name': class_list_data.get('groupName', group_login)
            },
            'learnerId': None,  # Set by frontend if viewing individual student
            'course_id': course_id,
            'course_name': course_structure.get('course_name', ''),
            'domain': course_structure.get('domain', '')
        }
        
        # Build groups array (for class average)
        class_average_state = {
            'topics': {}
        }
        
        # Calculate class averages
        for topic in topics:
            topic_name = topic['id']
            class_average_state['topics'][topic_name] = {
                'values': {},
                'overall': {'k': 0.0, 'p': 0.0}
            }
            
            # Calculate average for each resource
            for resource in resources:
                resource_name = resource['id']
                total_progress = 0.0
                count = 0
                
                for learner in learners:
                    topic_data = learner['state']['topics'].get(topic_name, {})
                    resource_data = topic_data.get('values', {}).get(resource_name, {})
                    if resource_data and 'p' in resource_data:
                        total_progress += resource_data['p']
                        count += 1
                
                avg_progress = total_progress / count if count > 0 else 0.0
                class_average_state['topics'][topic_name]['values'][resource_name] = {
                    'k': 0.0,
                    'p': avg_progress
                }
            
            # Calculate overall topic progress
            resource_values = list(class_average_state['topics'][topic_name]['values'].values())
            avg_topic_progress = sum(v['p'] for v in resource_values) / len(resource_values) if resource_values else 0.0
            class_average_state['topics'][topic_name]['overall'] = {
                'k': 0.0,
                'p': avg_topic_progress
            }
        
        return {
            'learners': learners,
            'topics': topics,
            'resources': resources,
            'groups': [
                {
                    'name': 'Class Average',
                    'state': class_average_state
                }
            ],
            'context': context
        }
    except Exception as e:
        logger.error(f"Error building analytics response: {str(e)}", exc_info=True)
        return {}


def get_all_students_progress_from_db(learner_ids: List[str], course_id: int, resource_names: List[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Batch fetch progress for multiple students efficiently.
    
    Args:
        learner_ids: List of student usernames/logins
        course_id: Course ID
        
    Returns:
        Dict mapping learner_id to progress data
    """
    if not learner_ids:
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
            
            logger.info(f"Batch fetching progress for {len(learner_ids)} students, course {course_id}")
            
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Use IN clause for batch query
                placeholders = ','.join(['%s'] * len(learner_ids))
                sql = f"""
                    SELECT 
                        user_id,
                        course_id,
                        model4topics,
                        model4content,
                        model4kc,
                        last_update
                    FROM `{agg_schema}`.ent_computed_models
                    WHERE user_id IN ({placeholders})
                      AND course_id = %s
                    ORDER BY user_id, last_update DESC
                """
                params = list(learner_ids) + [course_id]
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                
                # Group by user_id, taking the most recent for each
                result = {}
                seen_users = set()
                
                for row in rows:
                    user_id = row['user_id']
                    if user_id in seen_users:
                        continue  # Already have most recent for this user
                    seen_users.add(user_id)
                    
                    topics_data = parse_computed_model(row['model4topics'] or '', is_topics=True, resource_names=resource_names)
                    content_data = parse_computed_model(row['model4content'] or '', is_topics=False, resource_names=resource_names)
                    
                    result[user_id] = {
                        'topics': topics_data,
                        'content': content_data,
                        'last_update': row['last_update'].isoformat() if row['last_update'] else None
                    }
                
                # Count how many students have non-empty progress data
                students_with_progress = sum(1 for r in result.values() if r.get('topics'))
                logger.info(f"Found progress data for {len(result)} out of {len(learner_ids)} students")
                logger.info(f"Students with parsed progress data: {students_with_progress} (non-empty topics)")
                return result
        finally:
            db_conn.disconnect()
    except Exception as e:
        logger.error(f"Error batch fetching student progress: {str(e)}", exc_info=True)
        return {}

