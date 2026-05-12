# Automatic Group and Course ID Loading - Implementation Summary

## Overview

The dashboard now automatically attempts to discover and load KnowledgeTree Group IDs and Course IDs for authenticated users. The manual input fields remain available as a fallback option.

## Implementation Details

### Backend Components

#### 1. `kt_utils.py` - KnowledgeTree Utility Functions

**Functions:**
- `get_user_kt_groups(user)` - Gets user's KT groups from stored data or database
- `get_user_groups_from_db(kt_user_id)` - Queries KT database for group details
- `discover_course_ids_for_group(group_login, username, max_cid=20)` - Discovers Course IDs by testing API calls
- `get_user_groups_with_course_ids(user)` - Main function that combines group retrieval and Course ID discovery

**Course ID Discovery Strategy:**
- Tests Course IDs from 1 to `max_cid` (default: 20)
- Makes API calls to Aggregate service with each Course ID
- Validates responses by checking for course data indicators (`topics`, `context`)
- Returns list of valid Course IDs for each group

#### 2. `views.py` - Updated Views

**`legacy_dashboard(request)`:**
- Attempts to auto-discover groups and Course IDs on page load
- Passes `auto_groups` to template context
- Gracefully handles failures (falls back to manual input)

- Returns JSON with user's groups and discovered Course IDs
- Used by JavaScript for auto-population

### Frontend Components

#### 1. `dashboard_scripts.html` - JavaScript Auto-Loading

**`autoLoadUserGroups()` function:**
- Called automatically on page load
- Uses groups data provided by backend (fetched via direct database query in `legacy_dashboard` view)
- Auto-populates Group ID and Course ID fields
- Shows success/warning messages
- Displays quick-select dropdown if multiple groups/courses found

**Features:**
- Silent failure - if auto-load fails, manual input still works
- Auto-population of first available group/course
- Quick-select dropdown for multiple options
- Visual feedback with alert messages

#### 2. `dashboard_header.html` - Updated Labels

- Added helper text: "(Auto-filled if available)" to Group ID and Course ID labels
- Fields remain fully editable for manual override

## User Experience Flow

### Scenario 1: Auto-Load Success (Single Group/Course)
1. User loads dashboard
2. System automatically discovers groups and Course IDs
3. Fields are auto-populated
4. Success message shown: "Auto-loaded: [Group Name] (Course [ID])"
5. User can click "Launch Analytics" immediately

### Scenario 2: Auto-Load Success (Multiple Groups/Courses)
1. User loads dashboard
2. System discovers multiple groups or courses
3. First group/course is auto-populated
4. Quick-select dropdown appears for easy switching
5. User can select different group/course from dropdown

### Scenario 3: Auto-Load Failure
1. User loads dashboard
2. Auto-load fails silently (no error shown)
3. Manual input fields remain available
4. User can enter Group ID and Course ID manually
5. Normal functionality continues

### Scenario 4: Groups Found, No Course IDs
1. User loads dashboard
2. Groups are found but Course ID discovery fails
3. Warning message: "Groups found but no Course IDs discovered. Please enter manually."
4. User can manually enter Course ID

## Configuration

### Environment Variables

No new environment variables required. Uses existing KnowledgeTree configuration:
- `KT_AUTH_ENABLED` - Must be enabled
- `KT_API_URL` - Base URL for KnowledgeTree
- `KT_DB_*` - Database credentials (if using database method)

### Discovery Settings

Course ID discovery tests IDs from 1 to 20 by default. To change:
- Edit `max_cid` parameter in `discover_course_ids_for_group()` function
- Located in `modulearn/dashboard/kt_utils.py`

## Performance Considerations

### Course ID Discovery

- **Timeout**: 5 seconds per Course ID test
- **Max Course IDs**: 20 (configurable)
- **Total Time**: Up to 100 seconds in worst case (20 × 5s)
- **Optimization**: Discovery stops after finding valid Course IDs
- **Caching**: Consider implementing caching for discovered mappings

### Recommendations

1. **Cache Discovered Mappings**: Store Group → Course ID mappings in database after first discovery
2. **Background Discovery**: Run discovery in background, show results when ready
3. **User Feedback**: Show progress indicator during discovery
4. **Limit Discovery**: Only discover for first group initially, discover others on-demand

## Error Handling

### Graceful Degradation

- All auto-load failures are handled silently
- Manual input always available as fallback
- No errors shown to user unless explicitly needed
- Console logging for debugging

### Logging

- INFO: Successful group discovery
- WARNING: Groups found but no Course IDs
- ERROR: Database/API connection failures
- DEBUG: Detailed discovery process

## Future Enhancements

### Potential Improvements

1. **Mapping Table**: Create database table to store Group → Course ID mappings
2. **Admin Interface**: Allow admins to manually set mappings
3. **User Preferences**: Remember user's last selected group/course
4. **Batch Discovery**: Discover all Course IDs in background on first login
5. **Smart Caching**: Cache discovered mappings per user/group

## Testing

### Test Cases

1. **User with KT account, single group, single course**
   - Should auto-populate and be ready to use

2. **User with KT account, multiple groups**
   - Should show quick-select dropdown

3. **User with KT account, no Course IDs discovered**
   - Should show warning, allow manual entry

4. **User without KT account**
   - Should silently fail, manual input available

5. **Network/API failures**
   - Should gracefully fail, manual input available

## API Endpoints

### New Endpoint


**Response (Success):**
```json
{
  "success": true,
  "groups": [
    {
      "group_id": 123,
      "group_name": "Java Programming, Fall 2013",
      "group_login": "IS172013Fall",
      "course_ids": ["1", "2"]
    }
  ]
}
```

**Response (Error):**
```json
{
  "error": "User is not linked to a KnowledgeTree account",
  "groups": []
}
```

## Code References

- **Backend**: `modulearn/dashboard/kt_utils.py`
- **Views**: `modulearn/dashboard/views.py` (lines 66-95, new endpoint)
- **URLs**: `modulearn/dashboard/urls.py` (new route)
- **Frontend**: `modulearn/dashboard/templates/dashboard/components/dashboard_scripts.html` (auto-load functions)
- **Template**: `modulearn/dashboard/templates/dashboard/components/dashboard_header.html` (updated labels)

