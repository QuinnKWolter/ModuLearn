# Serving ModuLearn at adapt2.sis.pitt.edu/modulearn

The production Compose file sets the public domain, allowed hosts, CSRF origin,
proxy CORS origin, script prefix, static URL, and media URL. Its `environment`
entries take precedence over values in the production `.env`; secrets and
service-specific settings still come from `.env`.

On the adapt2 nginx host, route `/modulearn/` to port 20600 and strip that
prefix before forwarding to Django. Preserve the public host and HTTPS scheme:

```nginx
location = /modulearn { return 301 /modulearn/; }

location /modulearn-static/ {
    alias /var/www/html/modulearn-static/;
}

location /modulearn/ {
    proxy_pass http://127.0.0.1:20600/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

The deploy script copies collected static files to the nginx alias above.
With `SERVE_MEDIA_FILES=True`, Django handles `/modulearn/media/` through the
same proxy location. Keep existing nginx routes for PAWS, Aggregate, and other
services on adapt2 separate from `/modulearn/`. If nginx is on another host,
replace the upstream address and static-file path accordingly.
Restrict direct access to port 20600 to the trusted proxy, since Django uses
the proxy's `X-Forwarded-Proto` header to recognize HTTPS requests.

After deployment, check:

- `https://adapt2.sis.pitt.edu/modulearn/` and `/modulearn/admin/` load.
- `/modulearn-static/css/styles.<hash>.css` (or a static asset shown in page
  source) returns 200, and an existing `/modulearn/media/...` upload loads.
- The instructor's LTI Setup modal shows HTTPS URLs with `/modulearn/` for
  launch, login, JWKS, and cartridge configuration.
- A study's Copy Entry link starts with the new origin and retains Prolific's
  three template parameters.

Update the Tool URL, login URL, redirect URL, and JWKS URL registered in
Moodle or Canvas, and replace any Prolific study URL still pointing at the old
host. Existing browser sessions are scoped to the old host, so users sign in
again on adapt2. Course Authoring and KnowledgeTree/PAWS URLs are separate
services and should only change if those services move too.
