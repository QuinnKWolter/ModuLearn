"""
Database connection utilities for KnowledgeTree and Aggregate databases.
Supports both SSH tunneling (development) and direct connections (production).
"""

import logging
from typing import Optional, Tuple
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

# Try to import sshtunnel
try:
    from sshtunnel import SSHTunnelForwarder
    SSH_TUNNEL_AVAILABLE = True
except ImportError:
    SSH_TUNNEL_AVAILABLE = False
    logger.warning("sshtunnel not installed. SSH tunneling will not be available.")


class DatabaseConnection:
    """
    Manages database connections with optional SSH tunneling.
    """
    
    def __init__(self, host: str, port: int, user: str, password: str, database: str,
                 ssh_host: Optional[str] = None, ssh_port: int = 22, ssh_user: Optional[str] = None,
                 ssh_password: Optional[str] = None, ssh_key_path: Optional[str] = None,
                 use_ssh: bool = False):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        
        # SSH tunnel parameters
        self.use_ssh = use_ssh and ssh_host and ssh_host.strip() != ''
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_key_path = ssh_key_path
        
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
            logger.debug(f"Connecting to database - use_ssh={self.use_ssh}, host={self.host}, port={self.port}, "
                        f"ssh_host={self.ssh_host or 'None'}, ssh_user={self.ssh_user or 'None'}")
            
            # If SSH tunnel is required, set it up first
            if self.use_ssh:
                logger.info(f"Establishing SSH tunnel to {self.ssh_host}:{self.ssh_port} for database {self.host}:{self.port}")
                if not SSH_TUNNEL_AVAILABLE:
                    return False, "SSH tunneling not available. Please install sshtunnel: pip install sshtunnel"
                
                if not self.ssh_user:
                    return False, "SSH username is required when using SSH tunnel"
                
                # Create SSH tunnel
                try:
                    tunnel_params = {
                        'ssh_address_or_host': (self.ssh_host, self.ssh_port),
                        'ssh_username': self.ssh_user,
                        'remote_bind_address': (self.host, self.port),
                        'local_bind_address': ('127.0.0.1', 0)  # 0 = auto-assign port
                    }
                    
                    # Add authentication method
                    if self.ssh_key_path:
                        tunnel_params['ssh_pkey'] = self.ssh_key_path
                    elif self.ssh_password:
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
                logger.info(f"Attempting direct connection to {self.host}:{self.port} (no SSH tunnel)")
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
    
    # Log configuration for debugging (without sensitive data)
    use_ssh = db_config.get('USE_SSH', False)
    ssh_host = db_config.get('SSH_HOST', '')
    ssh_user = db_config.get('SSH_USER', '')
    
    logger.info(f"PAWS DB Connection - USE_SSH: {use_ssh}, HOST: {db_config.get('HOST')}, "
                f"SSH_HOST: {ssh_host or 'Not set'}, SSH_USER: {ssh_user or 'Not set'}, "
                f"USER: {db_config.get('USER', '')[:3] + '...' if db_config.get('USER') else 'Not set'}")
    
    # Warn if SSH credentials are provided but USE_SSH is False
    if not use_ssh and ssh_host and ssh_user:
        logger.warning(f"SSH credentials detected (SSH_HOST={ssh_host}, SSH_USER={ssh_user}) but USE_SSH=False. "
                      f"Connection will fail if database is not accessible directly. Set PAWS_DB_USE_SSH=True in .env")
    
    # Use aggregate schema as the default database (can query other schemas using schema.table syntax)
    return DatabaseConnection(
        host=db_config.get('HOST', '127.0.0.1'),
        port=db_config.get('PORT', 3306),
        user=db_config.get('USER', ''),
        password=db_config.get('PASSWORD', ''),
        database=db_config.get('AGGREGATE_SCHEMA', 'aggregate'),  # Default to aggregate schema
        ssh_host=db_config.get('SSH_HOST'),
        ssh_port=db_config.get('SSH_PORT', 22),
        ssh_user=db_config.get('SSH_USER'),
        ssh_password=db_config.get('SSH_PASSWORD'),
        ssh_key_path=db_config.get('SSH_KEY_PATH'),
        use_ssh=use_ssh
    )


# Legacy compatibility functions
def get_kt_db_connection():
    """Legacy: Get connection to PAWS database (same server, different schema)."""
    return get_paws_db_connection()


def get_aggregate_db_connection():
    """Legacy: Get connection to PAWS database (same server, different schema)."""
    return get_paws_db_connection()

