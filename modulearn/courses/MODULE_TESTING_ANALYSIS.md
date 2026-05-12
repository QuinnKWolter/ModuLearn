# Module Testing Analysis - Course Content Compatibility

## Test Course: "Testing the Course Authoring Tool"
**Source:** `paws-catalog_course-export_1767150246778.json`

---

## Critical Bugs Identified

### Bug #1: HTTP Proxy Not Being Used
**Symptom:** All HTTP content shows `Use proxy: false` even for allowed hosts
**Cause:** Code change removed `None` from protocol check:
```python
# Current (broken):
if content_url and selected_protocol in ('splice', 'pitt'):
# Should be:
if content_url and selected_protocol in ('splice', 'pitt', None):
```
**Impact:** HTTP content not proxied → mixed content blocked in HTTPS iframe

### Bug #2: LTI URL Routing Conflict
**Symptom:** LTI launches return "Invalid LTI launch request" (400)
**Cause:** Two routes map to `/lti/launch/`:
1. `lti/urls.py` → `lti.views.lti_launch` (Canvas inbound - expects POST)
2. `modulearn/urls.py` → `views_lti.launch` (Tool outbound - expects GET)

Django matches the Canvas route first, so tool launches fail.
**Fix:** Rename tool launch endpoint to `/lti/tool-launch/`

---

## Module-by-Module Analysis

### Unit 1

#### 1. Importance of Python (educvideos)
| Field | Value |
|-------|-------|
| Provider | `educvideos` |
| URL | `http://columbus.exp.sis.pitt.edu/educvideos/loadVideo.html?videoid=vd_video0001&sub=1` |
| Protocol | None |
| Status | ❌ **No content displayed** |

**Issue:** HTTP content not proxied (Bug #1)
**Fix:** Enable proxy for `columbus.exp.sis.pitt.edu`
**Prognosis:** ✅ Should work after Bug #1 fix

---

#### 2. Hello World (webex)
| Field | Value |
|-------|-------|
| Provider | `webex` |
| URL | `http://adapt2.sis.pitt.edu/web_ex_NV0FGdaHzy/Dissection2?act=pyt1.1&svc=progvis` |
| Protocol | None |
| Status | ❌ **403 Forbidden** |

**Issue:** Server returns 403 - likely requires authentication or specific parameters (`usr`, `grp`, `sid`)
**Analysis:** WebEx content appears to need PAWS session context. The URL has `usr=null&grp=null` which suggests missing user context.
**Fix:** May need to add user parameters to URL or use LTI launch
**Prognosis:** ⚠️ Requires server-side PAWS authentication

---

#### 3. PCRS sample problem 1 (pcrs)
| Field | Value |
|-------|-------|
| Provider | `pcrs` |
| URL | `https://pcrs.utm.utoronto.ca/mgrids/problems/python/1/embed?act=PCRS&sub=pcrs_sample_problem1` |
| Protocol | None |
| Status | ❌ **CSP blocks framing** |

**Issue:** Content Security Policy violation:
```
frame-ancestors http://adapt2.sis.pitt.edu http://pawscomp2.sis.pitt.edu https://proxy.personalized-learning.org
```
**Analysis:** PCRS server only allows framing from specific domains. ModuLearn's domain not in allowlist.
**Fix:** Contact PCRS administrators to add ModuLearn domain to CSP, OR proxy the content
**Prognosis:** ❌ External server configuration required

---

#### 4. BMI Calculator (pcex)
| Field | Value |
|-------|-------|
| Provider | `pcex` |
| URL | `http://pawscomp2.sis.pitt.edu/pcex/index.html?lang=PYTHON&set=py_bmi_calculator` |
| Protocol | None |
| Status | ⚠️ **Content loads, no grade updates** |

**Issue:** HTTP not proxied (Bug #1), no grade reporting
**Analysis:** PCEX content loads but doesn't report grades because:
1. Not going through proxy (Bug #1)
2. No SPLICE/LTI protocol configured
3. May need PAWS user context for grade reporting

**Fix:** 
1. Fix Bug #1 (proxy)
2. Check if PCEX supports SPLICE or needs LTI
**Prognosis:** ✅ Display will work after Bug #1; grades need protocol config

---

#### 5. Printing A Sequence of Repeated Numbers (pcex_ch)
| Field | Value |
|-------|-------|
| Provider | `pcex_ch` |
| URL | `http://pawscomp2.sis.pitt.edu/pcex/index.html?lang=PYTHON&set=py_repeated_sequence&ch=py_repeated_sequence2` |
| Protocol | None |
| Status | ⚠️ **Content loads, no grade updates** |

**Same as BMI Calculator**
**Prognosis:** ✅ Display will work after Bug #1; grades need protocol config

---

### Unit 2

#### 6. Modulo is Even (parsons)
| Field | Value |
|-------|-------|
| Provider | `parsons` |
| URL | `http://adapt2.sis.pitt.edu/acos/pitt/jsparsons/jsparsons-python/ps?example-id=ps_python_modulo_is_even` |
| Protocol | None |
| Status | ❌ **404 Not Found** |

**Issue:** Server returns 404 - content no longer exists
**Prognosis:** ❌ Dead content - needs to be removed or updated

---

#### 7. py_pythagorean_theorem (pcex_activity)
| Field | Value |
|-------|-------|
| Provider | `pcex_activity` |
| URL | `http://pawscomp2.sis.pitt.edu/pcex-authoring/assets/preview/index.html?load=...` |
| Protocol | None |
| Status | ⚠️ **Content loads, unexpected message origins** |

**Issue:** Console shows `Unexpected message origin: http://adapt2.sis.pitt.edu`
**Analysis:** Content is sending postMessage from adapt2 but allowlist only has `window.location.origin`
**Fix:** 
1. Fix Bug #1 (proxy) - then messages come from same origin
2. Or add adapt2 to allowed origins in module_frame.html
**Prognosis:** ✅ Should work after Bug #1

---

#### 8. Swap (animatedexamples)
| Field | Value |
|-------|-------|
| Provider | `animatedexamples` |
| URL | `http://acos.cs.hut.fi/pitt/jsvee/jsvee-python/ae?example-id=ae_adl_swap` |
| Protocol | None |
| Status | ❌ **404 Not Found** |

**Issue:** Server `acos.cs.hut.fi` redirects to `acos.cs.aalto.fi` which returns 404
**Analysis:** Domain changed (hut.fi → aalto.fi), content may have moved or been removed
**Prognosis:** ❌ Dead content or needs URL update

---

#### 9. addasm_indlabel (ctat)
| Field | Value |
|-------|-------|
| Provider | `ctat` |
| URL | `http://adapt2.sis.pitt.edu/lti/launch?tool=ctat&sub=addasm_indlabel` |
| Protocol | lti (auto-detected) |
| Status | ❌ **Invalid LTI launch request** |

**Issue:** LTI URL routing conflict (Bug #2)
**Log:** `INFO LTI launch request received` → hitting Canvas endpoint, not tool endpoint
**Fix:** Fix Bug #2 (rename tool launch endpoint)
**Prognosis:** ✅ Should work after Bug #2 fix (if CTAT credentials configured)

---

#### 10. Creating a Dictionary of Student-Scores Pairs (pcex_ch)
| Field | Value |
|-------|-------|
| Provider | `pcex_ch` |
| URL | `http://pawscomp2.sis.pitt.edu/pcex/index.html?lang=PYTHON&set=py_student_score&ch=py_score_dict2` |
| Protocol | None |
| Status | ⚠️ **Content loads, no grade updates** |

**Same as other PCEX content**
**Prognosis:** ✅ Display will work after Bug #1

---

### Unit 3

#### 11. pfe-1-3 (readingmirror)
| Field | Value |
|-------|-------|
| Provider | `readingmirror` |
| URL | `http://adapt2.sis.pitt.edu/ereader/reader/7/pfe-1-3/` |
| Protocol | None |
| Status | ❌ **500 Error + X-Frame-Options: deny** |

**Issues:** 
1. Server returns 500 Internal Server Error
2. X-Frame-Options: deny blocks embedding
**Analysis:** Server-side error AND explicit frame blocking
**Prognosis:** ❌ Server configuration issue

---

#### 12. Guess The Number Exercise (codeocean)
| Field | Value |
|-------|-------|
| Provider | `codeocean` |
| URL | `http://adapt2.sis.pitt.edu/lti/launch?tool=codeocean&sub=336c84ab` |
| Protocol | lti (auto-detected) |
| Status | ❌ **Invalid LTI launch request** |

**Issue:** LTI URL routing conflict (Bug #2)
**Fix:** Fix Bug #2
**Prognosis:** ✅ Should work after Bug #2 fix (if CodeOcean credentials configured)

---

#### 13. Variables 4 (quizpet)
| Field | Value |
|-------|-------|
| Provider | `quizpet` |
| URL | `http://adapt2.sis.pitt.edu/quizpet/displayQuiz.jsp?rdfID=Variables4&app=41&act=Variables&sub=Variables4` |
| Protocol | None |
| Status | ❌ **500 NullPointerException** |

**Issue:** Server-side Java error (NullPointerException)
**Analysis:** QuizPET service is broken on the server
**Prognosis:** ❌ Server-side bug needs fixing

---

#### 14. ebook-py-2-ch01-sec05-int1-1 (codecheck)
| Field | Value |
|-------|-------|
| Provider | `codecheck` |
| URL | `http://adapt2.sis.pitt.edu/lti/launch?tool=codecheck&sub=ebook-py-2-ch01-sec05-int1-1` |
| Protocol | lti (auto-detected) |
| Status | ❌ **Invalid LTI launch request** |

**Issue:** LTI URL routing conflict (Bug #2)
**Fix:** Fix Bug #2
**Prognosis:** ✅ Should work after Bug #2 fix (if CodeCheck credentials configured)

---

#### 15. Tree traversal. Challenge (pcex_ch)
| Field | Value |
|-------|-------|
| Provider | `pcex_ch` |
| URL | `http://adapt2.sis.pitt.edu/pcex/index.html?lang=PYTHON&set=py_trees_traversal&ch=traversal_ch` |
| Protocol | None |
| Status | ⚠️ **Content loads, no grade updates** |

**Same as other PCEX content**
**Prognosis:** ✅ Display will work after Bug #1

---

## Summary by Status

### ✅ Will Work After Bug Fixes (7 modules)
| Module | Provider | Fix Required |
|--------|----------|--------------|
| Importance of Python | educvideos | Bug #1 (proxy) |
| BMI Calculator | pcex | Bug #1 (proxy) |
| Printing A Sequence... | pcex_ch | Bug #1 (proxy) |
| py_pythagorean_theorem | pcex_activity | Bug #1 (proxy) |
| Creating a Dictionary... | pcex_ch | Bug #1 (proxy) |
| Tree traversal. Challenge | pcex_ch | Bug #1 (proxy) |
| addasm_indlabel | ctat | Bug #2 (LTI routing) + credentials |
| Guess The Number Exercise | codeocean | Bug #2 (LTI routing) + credentials |
| ebook-py-2-ch01-sec05-int1-1 | codecheck | Bug #2 (LTI routing) + credentials |

### ⚠️ Needs External Configuration (2 modules)
| Module | Provider | Issue |
|--------|----------|-------|
| Hello World | webex | Needs PAWS authentication |
| PCRS sample problem 1 | pcrs | CSP blocks framing from ModuLearn |

### ❌ Dead/Broken Content (4 modules)
| Module | Provider | Issue |
|--------|----------|-------|
| Modulo is Even | parsons | 404 Not Found |
| Swap | animatedexamples | 404 Not Found (domain changed) |
| pfe-1-3 | readingmirror | 500 Error + X-Frame-Options deny |
| Variables 4 | quizpet | 500 NullPointerException |

---

## Required Code Fixes

### Fix #1: Restore Proxy for Unknown Protocols ✅ DONE
```python
# courses/views.py - line ~311 and ~391
# Changed FROM:
if content_url and selected_protocol in ('splice', 'pitt'):
# Changed TO:
if content_url and selected_protocol in ('splice', 'pitt', None):
```

### Fix #2: Rename Tool Launch Endpoint ✅ DONE
```python
# modulearn/urls.py - line 27
# Changed FROM:
path("lti/launch/", views_lti.launch, name="lti_launch"),
# Changed TO:
path("lti/tool-launch/", views_lti.launch, name="lti_launch"),
```

### Fix #3: Add More Origins to postMessage Allowlist ✅ DONE
```javascript
// module_frame.html - PAWS domains added for non-proxied scenarios
const expectedOrigins = new Set([
  window.location.origin,              // ModuLearn origin (includes proxied content)
  'https://codecheck.me',              // External CodeCheck
  'https://codecheck.io',              // External CodeCheck
  'http://adapt2.sis.pitt.edu',        // PAWS content (if loaded directly)
  'http://pawscomp2.sis.pitt.edu',     // PAWS content (if loaded directly)
  'http://columbus.exp.sis.pitt.edu',  // PAWS content (if loaded directly)
  'https://adapt2.sis.pitt.edu',       // PAWS content (HTTPS variant)
  'https://pawscomp2.sis.pitt.edu',    // PAWS content (HTTPS variant)
  'https://columbus.exp.sis.pitt.edu', // PAWS content (HTTPS variant)
]);
```

---

## Provider Protocol Mapping (Recommended)

Based on URL patterns, here's what protocols each provider should use:

| Provider | URL Pattern | Recommended Protocol |
|----------|-------------|---------------------|
| `educvideos` | Direct HTML | `pitt` (proxy) |
| `webex` | Direct HTML + params | `pitt` (needs auth) |
| `pcrs` | HTTPS embed | `splice` (if supported) |
| `pcex`, `pcex_ch`, `pcex_activity` | Direct HTML | `pitt` (proxy) |
| `parsons` | ACOS content | `pitt` (if alive) |
| `animatedexamples` | ACOS content | `pitt` (if alive) |
| `ctat` | LTI launch URL | `lti` |
| `codeocean` | LTI launch URL | `lti` |
| `codecheck` | LTI launch URL | `lti` or `splice` |
| `readingmirror` | Direct HTML | `pitt` (needs server fix) |
| `quizpet` | JSP content | `pitt` (needs server fix) |

---

## Action Items

1. **✅ DONE:** Fix Bug #1 and Bug #2 
2. **✅ DONE:** Refactor LTI consumer with config-driven architecture (see `lti/config.py`)
3. **Short-term:** Configure LTI credentials in `.env`:
   ```bash
   # CodeCheck
   CODECHECK_KEY=your_key
   CODECHECK_SECRET=your_secret  
   CODECHECK_LAUNCH=https://codecheck.io/lti
   
   # CTAT
   CTAT_KEY=your_key
   CTAT_SECRET=your_secret
   CTAT_LAUNCH=https://preview.ctat.cs.cmu.edu/run_lti_problem_set/...
   
   # CodeOcean
   CODEOCEAN_KEY=your_key
   CODEOCEAN_SECRET=your_secret
   CODEOCEAN_LAUNCH=https://codeocean.openhpi.de/lti/launch
   ```
4. **Medium-term:** Contact PAWS team about dead content (parsons, animatedexamples, readingmirror, quizpet)
5. **Long-term:** Get course-authoring to provide `provider_protocols` mapping

---

## LTI Consumer Documentation

See `lti/LTI_CONSUMER_DOCUMENTATION.md` for complete documentation on:
- Environment variable configuration
- Adding new tools
- Production deployment (HTTPS, proxy headers, iframes)
- Troubleshooting

