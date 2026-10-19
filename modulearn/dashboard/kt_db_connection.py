"""
Database connection utilities for KnowledgeTree and Aggregate databases.
Uses direct MySQL connections; network access is configured by the deployment.
"""

import logging
from typing import Tuple
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

class DatabaseConnection:
    """
    Manages direct database connections.
    """
    
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None

    def connect(self) -> Tuple[bool, str]:
        """
        Connect directly to the configured MySQL host.
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # Connect to MySQL
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                cursorclass=DictCursor,
                connect_timeout=10,
                read_timeout=30,
            )
            
            return True, "Direct connection established successfully"
            
        except pymysql.Error as e:
            error_msg = f"Database connection error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def disconnect(self):
        """Close the database connection."""
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            finally:
                self.connection = None
        
    
    def get_connection(self):
        """Get the database connection object."""
        return self.connection


def get_paws_db_connection():
    """
    Get a connection to the PAWS MySQL database.
    This single database server contains multiple schemas:
    - portal_test2 (KnowledgeTree)
    - aggregate (Aggregate/Course data)
    
    Returns:
        DatabaseConnection object (call .connect() to establish connection)
    """
    from django.conf import settings
    db_config = getattr(settings, 'PAWS_DATABASE', {})
    
    if not db_config:
        raise ValueError("PAWS database not configured")
    
    # Use aggregate schema as the default database (can query other schemas using schema.table syntax)
    return DatabaseConnection(
        host=db_config.get('HOST', '127.0.0.1'),
        port=db_config.get('PORT', 3306),
        user=db_config.get('USER', ''),
        password=db_config.get('PASSWORD', ''),
        database=db_config.get('AGGREGATE_SCHEMA', 'aggregate'),  # Default to aggregate schema
    )


# Legacy compatibility functions
def get_kt_db_connection():
    """Legacy: Get connection to PAWS database (same server, different schema)."""
    return get_paws_db_connection()


def get_aggregate_db_connection():
    """Legacy: Get connection to PAWS database (same server, different schema)."""
    return get_paws_db_connection()

