"""Run the actual injected proxy script in Chrome; no external submissions."""
import os
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'modulearn.settings')
import django
django.setup()
from django.test import override_settings
from playwright.sync_api import sync_playwright, expect
from modulearn.views_proxy import _inject_activity_api_rewrite_script


class PcrsFeedbackTests(unittest.TestCase):
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
        self.page.set_content('<form><textarea>my unfinished code</textarea></form>')
        self.page.evaluate('''() => {
          window.XMLHttpRequest = class extends EventTarget {
            open(method, url) { this.url=url; }
            send() { setTimeout(()=>{this.status=window.replyStatus; this.dispatchEvent(new Event('loadend'));}, 2600); }
          };
          window.replyStatus=504;
          window.fetch=async (resource)=>({status:200,url:resource});
        }''')
        with override_settings(FORCE_SCRIPT_NAME='/modulearn/'):
            markup = _inject_activity_api_rewrite_script('<head></head>')
        script = re.search(r'<script>(.*?)</script>', markup, re.S)[1]
        self.page.add_script_tag(content=script)

    def tearDown(self):
        self.page.close()

    def test_wait_failure_code_preservation_and_successful_retry(self):
        self.page.evaluate('''() => {
          window.xhr=new XMLHttpRequest();
          xhr.open('POST','/modulearn//proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run');
          xhr.send();
        }''')
        status = self.page.locator('#modulearn-pcrs-status')
        expect(status).to_have_text('PCRS is still checking your code. Please wait before submitting again.')
        expect(status).to_be_visible()
        expect(status).to_have_text('No grading result was received. Your code is still in the editor. Please try submitting again shortly.')
        expect(self.page.locator('textarea')).to_have_value('my unfinished code')
        self.assertEqual(self.page.evaluate('xhr.url'), '/modulearn/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')
        self.page.evaluate("replyStatus=200; xhr.open('POST','/mgrids/problems/java/358/run'); xhr.send();")
        expect(status).to_be_visible(timeout=4000)
        expect(status).to_be_hidden(timeout=4000)
        self.assertEqual(self.page.evaluate('xhr.url'), '/modulearn/proxy/https/pcrs.utm.utoronto.ca/mgrids/problems/java/358/run')

    def test_unrelated_requests_do_not_show_grading_status(self):
        self.page.evaluate("const x=new XMLHttpRequest(); x.open('GET','/mgrids/static/example.js'); x.send();")
        expect(self.page.locator('#modulearn-pcrs-status')).to_have_count(0)


if __name__ == '__main__':
    unittest.main()
