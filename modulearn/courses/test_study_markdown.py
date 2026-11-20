from django.test import SimpleTestCase
from courses.templatetags.study_text import study_markdown


class StudyMarkdownTests(SimpleTestCase):
    def test_commonmark_blocks_and_gfm_extensions(self):
        html = study_markdown('''# Heading

1. First
2. Second
   - Nested **bold** and _italic_

- [ ] Pending
- [x] Finished

> Quote with ~~strikethrough~~

| Left | Right |
| :--- | ---: |
| `code` | **value** |

---

```python
print("<escaped>")
```

[Reference][ref] and https://example.org

[ref]: https://example.com "Title"
''')
        for fragment in ['<h1>Heading</h1>', '<ol>', '<ul>', '<strong>bold</strong>',
                         '<em>italic</em>', '<blockquote>', '<s>strikethrough</s>',
                         '<table>', 'text-align:right', '<code>code</code>',
                         '<hr>', 'class="language-python"', '&lt;escaped&gt;',
                         'href="https://example.com"', 'href="https://example.org"']:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)
        self.assertEqual(html.count('type="checkbox"'), 2)
        self.assertEqual(html.count('disabled="disabled"'), 2)
        self.assertEqual(html.count('checked="checked"'), 1)
        self.assertEqual(html.count('<label>'), 2)

    def test_html_and_executable_links_never_become_active(self):
        for text in ['<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
                     '[bad](javascript:alert%281%29)', '[bad](vbscript:evil)',
                     '[bad](file:///etc/passwd)', '![bad](data:image/png;base64,abc)',
                     '[bad](JaVaScRiPt:alert%281%29)', '[bad](javascript&#58;alert%281%29)']:
            with self.subTest(text=text):
                html = study_markdown(text)
                self.assertNotIn('<script', html)
                self.assertNotIn('<img', html)
                self.assertNotIn('href=', html)

    def test_images_escapes_headings_and_line_breaks(self):
        html = study_markdown('![Diagram](https://example.org/image.png "Caption")\n\n'
                              '\\*literal\\*\nnext line\n\n###### Small heading')
        self.assertIn('alt="Diagram"', html)
        self.assertIn('title="Caption"', html)
        self.assertIn('*literal*<br', html)
        self.assertIn('<h6>Small heading</h6>', html)
        self.assertNotIn('<em>', html)
        self.assertEqual(study_markdown(None), '')
