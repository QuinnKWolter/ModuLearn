"""Optional real-browser checks: python tests/browser/test_markdown_editor.py.

Requires Playwright and Chrome; no application server, accounts or database writes.
"""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]


class MarkdownEditorBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 800, 'height': 700})
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.set_content('<button id="outside">Outside</button><div id="editor" class="form-markdown-editor"></div><textarea hidden id="saved"></textarea>')
        for name in ['study-markdown.css', 'markdown-field.css']:
            self.page.add_style_tag(path=str(ROOT/'static/css'/name))
        self.page.add_script_tag(path=str(ROOT/'static/js/inline-markdown.generated.js'))
        self.page.evaluate('''() => { window.editor = ModuLearnInlineMarkdown.mount(document.querySelector('#editor'), {
            value:'', label:'Markdown', onChange:value=>document.querySelector('#saved').value=value
        }); }''')
        self.edit = self.page.locator('.cm-content')
        self.saved = self.page.locator('#saved')

    def tearDown(self):
        errors = self.errors[:]
        self.page.close()
        self.assertEqual(errors, [])

    def test_continue_and_exit_lists_quotes_and_nested_items(self):
        for original, expected in [('- First', '- First\n- '),
                                   ('3. First', '3. First\n4. '),
                                   ('- [x] Done', '- [x] Done\n- [ ] '),
                                   ('> Quote', '> Quote\n> '),
                                   ('- Parent\n    - Child', '- Parent\n    - Child\n    - ')]:
            with self.subTest(original=original):
                self.edit.fill(original)
                self.page.keyboard.press('Control+End')
                self.page.keyboard.press('Enter')
                expect(self.saved).to_have_value(expected)
                self.page.keyboard.press('Control+z')
                expect(self.saved).to_have_value(original)
        self.edit.fill('- First\n- ')
        self.page.keyboard.press('Control+End')
        self.page.keyboard.press('Enter')
        expect(self.saved).to_have_value('- First\n')
        self.edit.fill('- Parent\n- Child')
        self.page.keyboard.press('Control+End')
        self.page.keyboard.press('Control+]')
        expect(self.saved).to_have_value('- Parent\n    - Child')
        self.page.keyboard.press('Control+[')
        expect(self.saved).to_have_value('- Parent\n- Child')

    def test_typing_after_every_empty_toolbar_insertion(self):
        cases = [
            ('bullet','- Typed'), ('ordered','1. Typed'), ('task','- [ ] Typed'),
            ('heading','# Typed'), ('quote','> Typed'), ('bold','**Typed**'),
            ('italic','*Typed*'), ('strike','~~Typed~~'), ('code','`Typed`'),
            ('codeblock','```\nTyped\n```\n\n'), ('rule','---\n\nTyped'),
            ('link','[Typed](https://)'), ('image','![Typed](https://)'),
            ('table','| Typed | Column 2 |\n| --- | --- |\n| Text |  |\n\n'),
            ('indent','    Typed'), ('outdent','Typed'),
        ]
        for kind, expected in cases:
            with self.subTest(kind=kind):
                self.edit.fill('')
                self.page.evaluate('(kind)=>editor.format(kind)',kind)
                expect(self.edit).to_be_focused()
                self.page.keyboard.insert_text('Typed')
                expect(self.saved).to_have_value(expected)

    def test_prefix_changes_preserve_content_and_move_past_marker(self):
        for original,kind,expected in [
            ('Text','bullet','- TypedText'),
            ('- Text','task','- [ ] TypedText'),
            ('    ','bullet','    - Typed'),
            ('- Text','bullet','TypedText'),
        ]:
            with self.subTest(original=original,kind=kind):
                self.edit.fill(original)
                self.page.keyboard.press('Control+Home')
                self.page.evaluate('(kind)=>editor.format(kind)',kind)
                self.page.keyboard.insert_text('Typed')
                expect(self.saved).to_have_value(expected)
        self.edit.fill('Text')
        self.page.keyboard.press('Control+End')
        self.page.evaluate("editor.format('ordered')")
        self.page.keyboard.insert_text(' more')
        expect(self.saved).to_have_value('1. Text more')

    def test_link_destination_and_code_body_are_selected_without_erasing_structure(self):
        for kind,typed,expected in [
            ('link','https://example.org','[Label](https://example.org)'),
            ('image','https://example.org/image.png','![Label](https://example.org/image.png)'),
            ('codeblock','replacement','```\nreplacement\n```\n\n'),
        ]:
            with self.subTest(kind=kind):
                self.edit.fill('Label')
                self.page.keyboard.press('Control+a')
                self.page.evaluate('(kind)=>editor.format(kind)',kind)
                self.page.keyboard.insert_text(typed)
                expect(self.saved).to_have_value(expected)

    def test_rendered_table_task_toggle_and_exact_source_roundtrip(self):
        text = '# Heading\n\n| Left | Right |\n| :--- | ---: |\n| **bold** | `code` |\n\n- [ ] Pending\n- [x] Done\n\n~~struck~~'
        self.edit.fill(text)
        self.page.locator('#outside').focus()
        expect(self.page.locator('.cm-md-rendered table')).to_have_count(1)
        expect(self.page.locator('td strong')).to_have_text('bold')
        expect(self.page.locator('.cm-md-task')).to_have_count(2)
        expect(self.page.locator('.cm-md-strike')).to_have_text('struck')
        self.page.locator('.cm-md-task').first.click()
        expect(self.saved).to_have_value(text.replace('- [ ] Pending', '- [x] Pending'))
        self.page.evaluate('editor.focus()')
        self.page.keyboard.press('Control+z')
        expect(self.saved).to_have_value(text)
        self.page.evaluate('editor.source(true)')
        expect(self.page.locator('.cm-md-rendered')).to_have_count(0)
        expect(self.saved).to_have_value(text)
        self.page.evaluate('editor.source(false)')
        self.page.locator('#outside').focus()
        self.page.locator('.cm-md-rendered td').first.click()
        expect(self.page.locator('.cm-md-table-source')).to_have_count(3)
        expect(self.saved).to_have_value(text)

    def test_toolbar_selection_formatting_and_safe_rendering(self):
        self.edit.fill('First\nSecond')
        self.page.keyboard.press('Control+a')
        self.page.evaluate("editor.format('ordered')")
        expect(self.saved).to_have_value('1. First\n2. Second')
        self.page.evaluate("editor.format('task')")
        expect(self.saved).to_have_value('- [ ] First\n- [ ] Second')
        self.edit.fill('Text')
        self.page.keyboard.press('Control+a')
        self.page.evaluate("editor.format('bold')")
        expect(self.saved).to_have_value('**Text**')
        self.page.evaluate("editor.format('bold')")
        expect(self.saved).to_have_value('Text')
        text = '| Unsafe |\n| --- |\n| <img src=x onerror=alert(1)> |\n\n![bad](javascript:alert%281%29)'
        self.edit.fill(text)
        self.page.locator('#outside').focus()
        expect(self.page.locator('.cm-md-rendered img')).to_have_count(0)
        expect(self.saved).to_have_value(text)
        self.page.set_viewport_size({'width': 390, 'height': 700})
        self.assertLessEqual(self.page.locator('#editor').evaluate('(e)=>e.scrollWidth-e.clientWidth'), 1)

    def test_links_images_and_insert_controls_keep_markdown(self):
        self.page.route('https://example.org/image.png', lambda route: route.fulfill(status=204))
        text='[Documentation](https://example.org)\n\n![Diagram](https://example.org/image.png)'
        self.edit.fill(text)
        self.page.locator('#outside').focus()
        expect(self.page.locator('.cm-md-rendered a')).to_have_text('Documentation')
        expect(self.page.locator('.cm-md-rendered img')).to_have_attribute('alt','Diagram')
        self.page.locator('.cm-md-rendered.cm-md-link').click()
        expect(self.edit).to_be_focused()
        expect(self.saved).to_have_value(text)
        self.assertEqual(self.page.url, 'about:blank')
        for kind, fragment in [('table','| --- | --- |'),('link','](https://)'),
                               ('image','![Text]'),('codeblock','```\nText\n```'),('rule','---')]:
            with self.subTest(kind=kind):
                self.edit.fill('Text')
                self.page.keyboard.press('Control+a')
                self.page.evaluate('(kind)=>editor.format(kind)',kind)
                self.assertIn(fragment,self.saved.input_value())
                self.page.keyboard.press('Control+z')
                expect(self.saved).to_have_value('Text')

    def test_reusable_field_toolbar_reset_validation_and_teardown(self):
        self.page.add_script_tag(path=str(ROOT/'static/js/markdown-field.js'))
        self.page.evaluate('''() => {
          const form=document.createElement('form');form.id='reusable';
          form.innerHTML='<label class="original">Description<textarea name="description" required maxlength="255" data-markdown-editor>Default</textarea></label>';
          document.body.append(form);
        }''')
        field=self.page.locator('[name=description]')
        shell=self.page.locator('#reusable .form-markdown')
        edit=shell.locator('.cm-content')
        expect(edit).to_be_visible()
        for label in ['Insert link','Bulleted list','Numbered list']:
            expect(shell.get_by_role('button',name=label,exact=True).locator('svg')).to_have_count(1)
        edit.fill('')
        shell.get_by_role('button',name='Bulleted list',exact=True).click()
        self.page.keyboard.insert_text('Item')
        expect(field).to_have_value('- Item')
        self.assertEqual(self.page.evaluate("Object.fromEntries(new FormData(document.querySelector('#reusable')))"),{'description':'- Item'})
        self.page.evaluate("document.querySelector('#reusable').reset()")
        expect(field).to_have_value('Default')
        expect(edit).to_have_text('Default')
        edit.fill('')
        self.page.evaluate("document.querySelector('[name=description]').reportValidity()")
        expect(shell.locator('.form-markdown-error')).to_be_visible()
        expect(edit).to_be_focused()
        edit.fill('Fixed')
        expect(shell.locator('.form-markdown-error')).to_be_hidden()
        self.page.evaluate("ModuLearnMarkdownField.mount(document.querySelector('[name=description]')).destroy()")
        expect(shell).to_have_count(0)
        expect(field).to_be_visible()
        expect(self.page.locator('#reusable > label.original > textarea')).to_have_value('Fixed')


if __name__ == '__main__':
    unittest.main()
