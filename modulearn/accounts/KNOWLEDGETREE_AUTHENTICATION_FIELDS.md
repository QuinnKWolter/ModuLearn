# KnowledgeTree Authentication Fields

This document describes the fields from the PAWS/KnowledgeTree database that are used to populate user information when someone authenticates with KnowledgeTree credentials.

## Database Tables and Fields

### Primary Table: `ent_user`

When authenticating via **direct database access**, the following fields are queried:

```sql
SELECT UserID, Login, Name, Pass, email
FROM ent_user
WHERE Login = ? AND isGroup = 0
```

**Fields Used:**
- **`UserID`** → Maps to `User.kt_user_id` (IntegerField, unique)
- **`Login`** → Maps to `User.kt_login` (CharField, unique) and `User.username`
- **`Name`** → Maps to `User.full_name`
- **`Pass`** → Used for password verification (MD5 hash comparison)
- **`email`** → Maps to `User.email`

### Related Table: `rel_user_user`

For fetching user groups/courses:

```sql
SELECT u.Name
FROM rel_user_user ruu
LEFT JOIN ent_user u ON u.UserID = ruu.ParentUserID
WHERE ruu.ChildUserID = ?
```

**Fields Used:**
- **`ParentUserID`** → Links to group/course UserID
- **`ChildUserID`** → The authenticated user's UserID
- **`u.Name`** → Group/course names → Maps to `User.kt_groups` (JSONField, array of group names)

## API Authentication Fields

When authenticating via **REST API** (`/PortalServices/Auth`), the response includes:

**Response Fields:**
- **`usr`** → Maps to `User.kt_login` and `User.username`
- **`name`** → Maps to `User.full_name`
- **`email`** → Maps to `User.email`
- **`groups`** → Maps to `User.kt_groups` (JSONField, array of group names)

**Note:** The API does NOT return `UserID`, so `User.kt_user_id` may remain `None` when using API-only authentication.

## User Model Field Mapping

| KnowledgeTree Field | ModuLearn User Field | Type | Notes |
|---------------------|---------------------|------|-------|
| `ent_user.UserID` | `kt_user_id` | IntegerField (nullable, unique) | Only available via database auth |
| `ent_user.Login` | `kt_login` | CharField (nullable, unique) | Primary identifier |
| `ent_user.Login` | `username` | CharField | Used as ModuLearn username |
| `ent_user.Name` | `full_name` | CharField | User's display name |
| `ent_user.email` | `email` | EmailField | User's email address |
| `rel_user_user` groups | `kt_groups` | JSONField | Array of group/course names |
| N/A | `is_instructor` | BooleanField | Always set to `True` for KT users |
| N/A | `is_student` | BooleanField | Always set to `False` for KT users |

## Authentication Flow

1. **User enters credentials** → System authenticates against KnowledgeTree
2. **On success**, system retrieves:
   - UserID (if database auth)
   - Login/username
   - Name
   - Email
   - Groups (from `rel_user_user` join)
3. **User lookup/creation**:
   - First tries to find by `kt_user_id` (if available)
   - Then tries by `kt_login`
   - Then tries by `username`
   - If not found, creates new user with `is_instructor=True`
4. **Field updates**:
   - Updates `kt_user_id` if available and not set
   - Updates `kt_login` to match KnowledgeTree login
   - Updates `full_name` if not already set
   - Updates `email` if not already set
   - Updates `kt_groups` with current group membership

## Security Notes

- **Password Storage**: KnowledgeTree uses unsalted MD5 hashes (legacy limitation)
- **Password Verification**: System hashes provided password with MD5 and compares to stored `Pass` field
- **Session Management**: `/PortalServices/Auth` is stateless - does not create HTTP sessions
- **Protected Resources**: Accessing resources (Show servlet) requires browser-based authentication to get JSESSIONID cookie

## Example Data Flow

**Database Authentication:**
```
ent_user row:
  UserID: 12345
  Login: "jdoe"
  Name: "John Doe"
  email: "jdoe@pitt.edu"
  Pass: "5f4dcc3b5aa765d61d8327deb882cf99" (MD5 hash)

rel_user_user rows:
  ChildUserID: 12345, ParentUserID: 67890 → Group: "CS101"
  ChildUserID: 12345, ParentUserID: 67891 → Group: "CS102"

Result:
  User.kt_user_id = 12345
  User.kt_login = "jdoe"
  User.username = "jdoe"
  User.full_name = "John Doe"
  User.email = "jdoe@pitt.edu"
  User.kt_groups = ["CS101", "CS102"]
  User.is_instructor = True
  User.is_student = False
```

**API Authentication:**
```
API Response:
{
  "loggedin": true,
  "usr": "jdoe",
  "name": "John Doe",
  "email": "jdoe@pitt.edu",
  "groups": ["CS101", "CS102"]
}

Result:
  User.kt_user_id = None (not provided by API)
  User.kt_login = "jdoe"
  User.username = "jdoe"
  User.full_name = "John Doe"
  User.email = "jdoe@pitt.edu"
  User.kt_groups = ["CS101", "CS102"]
  User.is_instructor = True
  User.is_student = False
```

