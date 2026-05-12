# Questions for KnowledgeTree Developer - Course ID Discovery

## Current Implementation Issue

We're currently using a brute-force approach to discover Course IDs by testing Course IDs 1-500 (configurable) via API calls. This is:
- **Slow**: Can take 5+ seconds per group
- **Inefficient**: Makes many unnecessary API calls
- **Limited**: May miss Course IDs outside the tested range

## Questions

### 1. Direct Database Query
**Question**: Can we query the Aggregate database directly to get Course IDs associated with a Group Login?

**What we need**:
- Database connection details for Aggregate database
- Table/column names that store the Group → Course ID mapping
- Example SQL query to get Course IDs for a group

**Example query we're looking for**:
```sql
SELECT DISTINCT course_id 
FROM [table_name] 
WHERE group_login = ? OR group_name = ?
```

### 2. API Endpoint for Course IDs
**Question**: Is there an existing API endpoint that returns available Course IDs for a given Group Login?

**What we need**:
- Endpoint URL (e.g., `/aggregate/GetCourseIdsForGroup?grp=GROUP_LOGIN`)
- Request format
- Response format

**Example**:
```
GET /aggregate/GetCourseIdsForGroup?grp=IS172013Fall
Response: { "course_ids": ["1", "2", "417"] }
```

### 3. Course ID Range/Format
**Question**: What is the typical range and format of Course IDs?

**What we need**:
- Typical range (e.g., 1-1000, or can they be much larger?)
- Format (always numeric, or can they be strings/alphanumeric?)
- Are Course IDs sequential or can they have gaps?

### 4. Group → Course ID Relationship
**Question**: What is the relationship between Group Login and Course ID?

**What we need**:
- Can one Group have multiple Course IDs? (We assume yes)
- Can multiple Groups share the same Course ID? (We assume yes)
- Is there a many-to-many relationship table we can query?

### 5. User-Specific Course IDs
**Question**: Are Course IDs user-specific or group-specific?

**What we need**:
- Should we query Course IDs per user, or per group?
- Are there Course IDs that a user has access to that aren't in their groups?

### 6. Aggregate Database Schema
**Question**: Can you provide or point us to the Aggregate database schema?

**What we need**:
- Table names related to courses/groups
- Column names that link groups to courses
- Sample data structure

## Current Workaround

Until we have a better solution, we're:
1. Testing Course IDs 1-500 (configurable via `KT_COURSE_ID_DISCOVERY_MAX`)
2. Only discovering Course IDs when a group is selected (on-demand)
3. Caching results would be the next optimization

## Preferred Solution

**Ideal approach**: Direct database query or API endpoint that returns Course IDs for a group without brute-force testing.

**Fallback**: If brute-force is necessary, we need to know:
- Maximum Course ID value to test
- Whether Course IDs are sequential or have patterns
- Any way to narrow down the search space

---

**Please provide answers to these questions so we can implement an efficient solution.**

