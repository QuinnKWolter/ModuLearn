"""Interactive preview UI checks; isolated DOM, no app data or provider traffic."""
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]


class ActivityPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_content('''<section data-module-block data-module-id="7" data-activity-type="form">
            <input name="module_7_title" value="Unsaved title"><button data-preview-activity>Preview</button>
            <div class="cfg-form-content-panel"></div></section>''')
        self.page.evaluate('''() => {
          window.sent=[];
          window.ModuLearnMarkdown={renderActivity:async data=>{
            sent.push(data);
            return '<div data-preview-form><fieldset data-require-choice><input type="checkbox" aria-label="Agree"></fieldset><button>Continue</button></div>';
          }};
        }''')
        self.page.add_script_tag(path=str(ROOT/'static/js/form-validation.js'))
        self.page.add_script_tag(path=str(ROOT/'static/js/activity-preview.js'))

    def tearDown(self):
        self.page.close()

    def test_form_validation_completion_reset_and_no_navigation(self):
        self.page.get_by_role('button',name='Preview',exact=True).click()
        dialog=self.page.get_by_role('dialog')
        dialog.get_by_role('button',name='Continue').click()
        expect(dialog.get_by_text('Preview completed.',exact=False)).to_have_count(0)
        dialog.get_by_label('Agree').check()
        dialog.get_by_role('button',name='Continue').click()
        expect(dialog.get_by_text('Preview completed. No responses were saved.')).to_be_visible()
        dialog.get_by_role('button',name='Restart Preview').click()
        expect(dialog.get_by_label('Agree')).not_to_be_checked()
        self.assertEqual(self.page.url,'about:blank')
        self.assertEqual(self.page.evaluate('sent.length'),1)

    def test_embedded_content_is_removed_when_closed_and_focus_returns(self):
        self.page.evaluate('''ModuLearnMarkdown.renderActivity=async data=>'<iframe src="about:blank" title="Activity"></iframe>' ''')
        self.page.get_by_role('button',name='Preview',exact=True).click()
        expect(self.page.locator('dialog iframe')).to_have_count(1)
        self.page.keyboard.press('Escape')
        expect(self.page.locator('dialog iframe')).to_have_count(0)
        expect(self.page.get_by_role('button',name='Preview',exact=True)).to_be_focused()


if __name__ == '__main__':
    unittest.main()
