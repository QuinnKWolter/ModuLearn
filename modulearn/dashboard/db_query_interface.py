"""
Database Query Interface for testing MySQL connections and queries.

This is a temporary testing tool to explore database schemas.
Should be restricted to admin/development use only.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

# Try to import sshtunnel, but make it optional
try:
    from sshtunnel import SSHTunnelForwarder
    SSH_TUNNEL_AVAILABLE = True
except ImportError:
    SSH_TUNNEL_AVAILABLE = False
    logger.warning("sshtunnel not installed. SSH tunneling will not be available.")


class DatabaseQueryInterface:
    """
    Interface for querying MySQL databases for testing and exploration.
    Supports both direct connections and SSH tunneled connections.
    """
    
    def __init__(self, host: str, port: int, user: str, password: str, database: str,
                 ssh_host: Optional[str] = None, ssh_port: int = 22, ssh_user: Optional[str] = None,
                 ssh_password: Optional[str] = None, ssh_key_path: Optional[str] = None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        
        # SSH tunnel parameters
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_key_path = ssh_key_path
        self.use_ssh = ssh_host is not None and ssh_host.strip() != ''
        
        self.connection = None
        self.ssh_tunnel = None
        self.local_bind_port = None
    
    def connect(self) -> Tuple[bool, str]:
        """
        Connect to the database, optionally through an SSH tunnel.
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # If SSH tunnel is required, set it up first
            if self.use_ssh:
                if not SSH_TUNNEL_AVAILABLE:
                    return False, "SSH tunneling not available. Please install sshtunnel: pip install sshtunnel"
                
                if not self.ssh_user:
                    return False, "SSH username is required when using SSH tunnel"
                
                # Create SSH tunnel
                try:
                    # Determine authentication method
                    ssh_auth = None
                    if self.ssh_key_path:
                        # Use key file authentication
                        ssh_auth = self.ssh_key_path
                    elif self.ssh_password:
                        # Use password authentication
                        ssh_auth = self.ssh_password
                    else:
                        return False, "SSH authentication required: provide either SSH password or SSH key path"
                    
                    # Build SSH tunnel parameters
                    tunnel_params = {
                        'ssh_address_or_host': (self.ssh_host, self.ssh_port),
                        'ssh_username': self.ssh_user,
                        'remote_bind_address': (self.host, self.port),
                        'local_bind_address': ('127.0.0.1', 0)  # 0 = auto-assign port
                    }
                    
                    # Add authentication method
                    if self.ssh_key_path:
                        # Use key file authentication
                        tunnel_params['ssh_pkey'] = self.ssh_key_path
                    elif self.ssh_password:
                        # Use password authentication
                        tunnel_params['ssh_password'] = self.ssh_password
                    else:
                        return False, "SSH authentication required: provide either SSH password or SSH key path"
                    
                    self.ssh_tunnel = SSHTunnelForwarder(**tunnel_params)
                    
                    self.ssh_tunnel.start()
                    self.local_bind_port = self.ssh_tunnel.local_bind_port
                    
                    logger.info(f"SSH tunnel established. Local port: {self.local_bind_port}")
                    
                    # Connect through tunnel (use localhost and tunnel's local port)
                    db_host = '127.0.0.1'
                    db_port = self.local_bind_port
                except Exception as e:
                    error_msg = f"SSH tunnel error: {str(e)}"
                    logger.error(error_msg)
                    return False, error_msg
            else:
                # Direct connection
                db_host = self.host
                db_port = self.port
            
            # Connect to MySQL
            self.connection = pymysql.connect(
                host=db_host,
                port=db_port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                cursorclass=DictCursor,
                connect_timeout=10,
                read_timeout=30,
            )
            
            connection_type = "SSH tunneled" if self.use_ssh else "Direct"
            return True, f"{connection_type} connection established successfully"
            
        except pymysql.Error as e:
            error_msg = f"Database connection error: {str(e)}"
            logger.error(error_msg)
            self._cleanup_ssh_tunnel()
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            self._cleanup_ssh_tunnel()
            return False, error_msg
    
    def disconnect(self):
        """Close database connection and SSH tunnel."""
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
            finally:
                self.connection = None
        
        self._cleanup_ssh_tunnel()
    
    def _cleanup_ssh_tunnel(self):
        """Close SSH tunnel if it exists."""
        if self.ssh_tunnel:
            try:
                self.ssh_tunnel.stop()
            except:
                pass
            finally:
                self.ssh_tunnel = None
                self.local_bind_port = None
    
    def execute_query(self, query: str, max_rows: int = 100) -> Tuple[bool, Optional[List[Dict]], str, Optional[int]]:
        """
        Execute a SQL query and return results.
        
        Args:
            query: SQL query string
            max_rows: Maximum number of rows to return (for safety)
        
        Returns:
            (success: bool, results: List[Dict] or None, message: str, row_count: int or None)
        """
        if not self.connection:
            return False, None, "Not connected to database. Please connect first.", None
        
        # Basic safety check - only allow SELECT queries
        query_upper = query.strip().upper()
        if not query_upper.startswith('SELECT'):
            return False, None, "Only SELECT queries are allowed for safety.", None
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                
                # Get all results
                rows = cursor.fetchall()
                row_count = len(rows)
                
                # Limit results for display
                if row_count > max_rows:
                    rows = rows[:max_rows]
                    message = f"Query returned {row_count} rows. Showing first {max_rows} rows."
                else:
                    message = f"Query returned {row_count} rows."
                
                # Convert to list of dicts
                results = [dict(row) for row in rows]
                
                return True, results, message, row_count
                
        except pymysql.Error as e:
            error_msg = f"Query error: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg, None
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg, None
    
    def get_tables(self) -> Tuple[bool, Optional[List[str]], str]:
        """
        Get list of all tables in the database.
        
        Returns:
            (success: bool, tables: List[str] or None, message: str)
        """
        if not self.connection:
            return False, None, "Not connected to database."
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                rows = cursor.fetchall()
                
                # Extract table names (column name varies by MySQL version)
                tables = []
                for row in rows:
                    # Table name is in the first column
                    table_name = list(row.values())[0]
                    tables.append(table_name)
                
                return True, sorted(tables), f"Found {len(tables)} tables"
                
        except Exception as e:
            return False, None, f"Error getting tables: {str(e)}"
    
    def describe_table(self, table_name: str) -> Tuple[bool, Optional[List[Dict]], str]:
        """
        Get table structure (columns, types, etc.).
        
        Returns:
            (success: bool, columns: List[Dict] or None, message: str)
        """
        if not self.connection:
            return False, None, "Not connected to database."
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"DESCRIBE `{table_name}`")
                rows = cursor.fetchall()
                columns = [dict(row) for row in rows]
                return True, columns, f"Table {table_name} has {len(columns)} columns"
        except Exception as e:
            return False, None, f"Error describing table: {str(e)}"
    
    def search_tables_for_columns(self, search_term: str) -> Tuple[bool, Optional[List[Dict]], str]:
        """
        Search for tables/columns containing a search term.
        
        Args:
            search_term: Term to search for (e.g., "course", "cid", "group")
        
        Returns:
            (success: bool, results: List[Dict] or None, message: str)
        """
        if not self.connection:
            return False, None, "Not connected to database."
        
        try:
            query = """
                SELECT 
                    TABLE_NAME,
                    COLUMN_NAME,
                    DATA_TYPE,
                    COLUMN_TYPE,
                    IS_NULLABLE,
                    COLUMN_KEY,
                    COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
                  AND (COLUMN_NAME LIKE %s OR TABLE_NAME LIKE %s)
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            
            with self.connection.cursor() as cursor:
                search_pattern = f"%{search_term}%"
                cursor.execute(query, (self.database, search_pattern, search_pattern))
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                return True, results, f"Found {len(results)} matching columns/tables"
        except Exception as e:
            return False, None, f"Error searching: {str(e)}"

