"""Resolve legacy catalog entry points without leaving the tracked iframe."""

import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


def normalize_activity_launch_url(url: str) -> str:
    if not url:
        return url
    parsed = urlsplit(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.hostname in {'pawscomp2.sis.pitt.edu', 'adapt2.sis.pitt.edu'}
        and parsed.path == '/pcex-authoring/preview/index.html'
    ):
        source = urlsplit(params.get('load', [''])[0])
        match = re.fullmatch(r'/pcex-authoring/api/hub/([a-fA-F0-9]{24})', source.path)
        if source.hostname not in {'pawscomp2.sis.pitt.edu', 'adapt2.sis.pitt.edu'} or not match:
            return url
        # The preview page is now a JS redirect to ACOS. Bypass it: otherwise
        # it escapes our proxy and ACOS rejects the HTTP hub URL as mixed content.
        params['load'] = [f'https://acos.cs.vt.edu/static/acos-pcex-examples/data/{match[1]}.json']
        params['example-id'] = ['preview']
        return urlunsplit((
            'https', 'acos.cs.vt.edu', '/pitt/acos-pcex/acos-pcex-examples/',
            urlencode(params, doseq=True), parsed.fragment,
        ))
    if (
        parsed.hostname == 'acos.cs.vt.edu'
        and parsed.path == '/pitt/jsvee/jsvee-java/ae'
        and params.get('example-id')
    ):
        example_id = params.pop('example-id')[0]
        if re.fullmatch(r'[\w.-]+', example_id):
            return urlunsplit((
                'https', parsed.netloc, f'/html/jsvee/jsvee-java/{example_id}',
                urlencode(params, doseq=True), parsed.fragment,
            ))
    return url
