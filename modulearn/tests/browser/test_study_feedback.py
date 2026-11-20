"""Browser checks for study feedback without changing provider event persistence."""
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]


class StudyFeedbackTests(unittest.TestCase):
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
        self.page.set_content('<body class="study-shell"><iframe id="content-iframe" srcdoc="Provider feedback"></iframe></body>')
        self.page.evaluate('''() => {
            window.savedEvents = []; window.failSave = false;
            window.moduleFrameConfig = {progressUrl:'/progress', courseInstanceId:1};
            window.fetch = async (url, options) => {
                savedEvents.push(JSON.parse(options.body));
                return {ok:!failSave, status:failSave?403:200,
                    json:async()=>({module_progress:{is_complete:true}})};
            };
        }''')
        self.page.add_script_tag(path=str(ROOT/'static/js/courses/module-frame.js'))
        self.page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")

    def tearDown(self):
        self.page.close()

    def answer(self):
        self.page.evaluate('''() => window.dispatchEvent(new MessageEvent('message', {
            source:document.querySelector('iframe').contentWindow, origin:location.origin,
            data:{type:'cupcake:log', activityType:'free-coding', eventName:'answerChecked',
                eventData:{isCorrect:false, testCasesResults:[{passed:false}]}}
        }))''')

    def test_study_saves_answer_without_course_advice(self):
        self.answer()
        self.page.wait_for_function('savedEvents.length === 1')
        expect(self.page.locator('#activity-save-status')).to_have_count(0)
        self.assertEqual(self.page.evaluate('savedEvents[0].provider_event.message.eventName'), 'answerChecked')

    def test_failed_save_remains_visible_and_retry_clears_it(self):
        self.page.evaluate('failSave = true')
        self.answer()
        expect(self.page.locator('#activity-save-status')).to_contain_text('could not be saved')
        self.page.evaluate('failSave = false')
        self.answer()
        self.page.wait_for_function('savedEvents.length === 2')
        expect(self.page.locator('#activity-save-status')).to_have_count(0)

    def test_regular_course_keeps_saved_status(self):
        self.page.evaluate("document.body.classList.remove('study-shell')")
        self.answer()
        expect(self.page.locator('#activity-save-status')).to_contain_text('Attempt saved')


if __name__ == '__main__':
    unittest.main()
