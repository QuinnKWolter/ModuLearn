#!/usr/bin/env python3
"""
Environment setup script for ModuLearn Django project.
This script helps you set the appropriate environment variables for development or production.
"""

import os
import sys
from pathlib import Path

def set_development_env():
    """Set environment variables for development"""
    os.environ['DEBUG'] = 'true'
    os.environ['DJANGO_DEVELOPMENT'] = 'true'
    os.environ['DEVELOPMENT'] = 'true'
    print("✅ Development environment variables set")
    print("   DEBUG=true, DJANGO_DEVELOPMENT=true, DEVELOPMENT=true")

def set_production_env():
    """Set environment variables for production"""
    os.environ['DEBUG'] = 'false'
    os.environ['DJANGO_PRODUCTION'] = 'true'
    os.environ['PRODUCTION'] = 'true'
    print("✅ Production environment variables set")
    print("   DEBUG=false, DJANGO_PRODUCTION=true, PRODUCTION=true")

def show_current_env():
    """Show current environment variables"""
    print("Current environment variables:")
    env_vars = ['DEBUG', 'DJANGO_DEVELOPMENT', 'DEVELOPMENT', 'DJANGO_PRODUCTION', 'PRODUCTION', 'HOSTNAME', 'SERVER_NAME']
    for var in env_vars:
        value = os.getenv(var, 'Not set')
        print(f"   {var}={value}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python set_env.py [dev|prod|show]")
        print("  dev  - Set development environment")
        print("  prod - Set production environment")
        print("  show - Show current environment variables")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'dev':
        set_development_env()
    elif command == 'prod':
        set_production_env()
    elif command == 'show':
        show_current_env()
    else:
        print(f"Unknown command: {command}")
        print("Use 'dev', 'prod', or 'show'")

if __name__ == '__main__':
    main()
