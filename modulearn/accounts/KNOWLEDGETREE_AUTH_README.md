# KnowledgeTree Authentication Integration

This document describes the KnowledgeTree authentication integration for ModuLearn.

## Overview

ModuLearn now supports authentication against KnowledgeTree as an additional authentication layer. Users can sign in using their KnowledgeTree credentials by checking the "Sign in with KnowledgeTree credentials" checkbox on the login page.

## Features

- **Dual Authentication Methods**: Supports both REST API and direct database access
- **Automatic Fallback**: Falls back to database if API is unavailable (when configured)
- **Auto Account Creation**: Automatically creates ModuLearn accounts for KnowledgeTree users on first login
- **Rate Limiting**: Implements rate limiting to prevent brute force attacks
- **Comprehensive Logging**: Logs all authentication attempts and outcomes

## Configuration

### Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Enable/disable KnowledgeTree authentication
KT_AUTH_ENABLED=True

# Authentication method: 'api', 'database', or 'both'
KT_AUTH_METHOD=api

# Fallback to database if API fails (only when AUTH_METHOD=api)
KT_AUTH_FALLBACK=True

# REST API Configuration
KT_API_URL=http://adapt2.sis.pitt.edu
KT_API_TIMEOUT=10

# Database Configuration (required if AUTH_METHOD is 'database' or 'both')
KT_DB_HOST=knowledge-tree-db.example.com
KT_DB_PORT=3306
KT_DB_NAME=knowledgetree
KT_DB_USER=readonly_user
KT_DB_PASSWORD=secure_password_here
```

### Settings

The configuration is automatically loaded in `settings.py` from environment variables. No manual configuration needed.

## Authentication Methods

### 1. REST API (Recommended)

Uses the `/PortalServices/Auth` endpoint:
- **URL**: `{KT_API_URL}/PortalServices/Auth`
- **Method**: GET
- **Parameters**: `usr` (username), `pwd` (MD5 hash of password)
- **Response**: JSON with `loggedin`, `usr`, `name`, `email`, `groups`

**Note**: The API returns username, not UserID. User matching is done by `kt_login` (username).

### 2. Direct Database Access

Connects directly to KnowledgeTree MySQL database:
- **Table**: `ent_user`
- **Query**: `SELECT UserID, Login, Name, Pass, email FROM ent_user WHERE Login = ? AND isGroup = 0`
- **Password Validation**: Compares MD5 hash of provided password with stored `Pass` column

**Note**: Requires `pymysql` package and database credentials.

## User Model Changes

The `User` model has been extended with KnowledgeTree fields:

- `kt_user_id` (IntegerField, nullable, unique): KnowledgeTree UserID (from database)
- `kt_login` (CharField, nullable, unique): KnowledgeTree username/login
- `kt_groups` (JSONField): List of KnowledgeTree groups/courses the user belongs to

## Authentication Flow

1. User enters username and password on login page
2. User checks "Sign in with KnowledgeTree credentials" checkbox
3. System attempts KnowledgeTree authentication:
   - If `AUTH_METHOD=api`: Tries API first, falls back to DB if `AUTH_FALLBACK=True`
   - If `AUTH_METHOD=database`: Uses database directly
   - If `AUTH_METHOD=both`: Tries API, then database
4. On success:
   - Finds existing ModuLearn user by `kt_login` or creates new one
   - Updates user data from KnowledgeTree (name, email, groups)
   - Creates Django session and logs user in
5. On failure:
   - Shows generic error message (for security)
   - Logs detailed error server-side

## Rate Limiting

Rate limiting is implemented to prevent brute force attacks:
- **Default**: 5 attempts per 15 minutes per username
- **Storage**: Django cache (database cache backend)
- **Reset**: Automatically resets on successful authentication

## Security Considerations

1. **MD5 Hashing**: KnowledgeTree uses unsalted MD5, which is cryptographically weak. This is a legacy limitation.
2. **HTTPS**: Ensure all API requests use HTTPS in production
3. **Rate Limiting**: Implemented to prevent brute force attacks
4. **Error Messages**: Generic error messages shown to users (don't reveal valid usernames)
5. **Logging**: Detailed logs for debugging, but passwords are never logged

## Troubleshooting

### API Connection Errors

If you see "Authentication service temporarily unavailable":
- Check `KT_API_URL` is correct
- Verify network connectivity to KnowledgeTree server
- Check if KnowledgeTree service is running
- Review server logs for detailed error messages

### Database Connection Errors

If using database authentication:
- Verify `pymysql` is installed: `pip install pymysql`
- Check database credentials are correct
- Verify network access to database server
- Check firewall rules

### User Not Found

If authentication succeeds but user creation fails:
- Check for username conflicts in ModuLearn
- Review logs for account linking issues
- Verify `kt_login` field is unique (should be automatically handled)

## Testing

To test the integration:

1. **Enable KnowledgeTree authentication**:
   ```bash
   KT_AUTH_ENABLED=True
   KT_AUTH_METHOD=api
   KT_API_URL=http://adapt2.sis.pitt.edu
   ```

2. **Test with valid KnowledgeTree credentials**:
   - Go to login page
   - Enter KnowledgeTree username and password
   - Check "Sign in with KnowledgeTree credentials"
   - Submit form

3. **Verify account creation**:
   - Check that new user was created in ModuLearn
   - Verify `kt_login` and `kt_groups` are populated
   - Check logs for successful authentication

## Migration

After setting up, run migrations:

```bash
python manage.py migrate accounts
```

This will add the KnowledgeTree fields to the User model.

## Dependencies

- `requests` - For REST API calls (already in requirements.txt)
- `pymysql` - For database access (added to requirements.txt, only needed if using database method)

## Logging

Authentication events are logged at different levels:

- **INFO**: Successful authentications
- **WARNING**: Failed authentications (invalid credentials)
- **ERROR**: System errors (API down, DB errors, etc.)
- **DEBUG**: Detailed flow (only in development)

Check Django logs for authentication events.

## Future Enhancements

Potential improvements:
- Support for email-based authentication (KnowledgeTree API supports this)
- Role mapping from KnowledgeTree groups to ModuLearn roles
- Synchronization of user data from KnowledgeTree
- Support for password migration from KnowledgeTree to Django

