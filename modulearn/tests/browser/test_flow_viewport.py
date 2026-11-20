"""Run with python tests/browser/test_flow_viewport.py (Playwright + Chrome).

Uses an isolated DOM; no server, accounts, or database writes.
"""
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]


class FlowViewportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1000, 'height': 800})
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.set_content('''
          <button id="outside">Open</button><div id="modal">
          <input data-flow-search aria-label="Search">
          <button data-flow-zoom-out>−</button><output data-flow-zoom-level></output>
          <button data-flow-zoom-in>+</button><button data-flow-fit>Fit</button>
          <button data-flow-reset>Reset</button><button data-flow-focus-view>Focus</button>
          <div id="shell" tabindex="0"><div id="map"><button class="is-related">Activity</button></div></div>
          <button id="last">Close</button></div>
          <style>
          #shell{width:600px;height:400px;overflow:auto;position:relative}
          .cfg-flow-stage{position:relative;overflow:hidden}
          #map{width:2000px;height:1000px;position:absolute;transform-origin:0 0}
          #map button{position:absolute;left:1200px;top:600px;width:150px;height:60px}
          </style>''')
        self.page.add_script_tag(path=str(ROOT/'static/js/flow-viewport.js'))
        self.page.evaluate('''() => {
          window.mount = () => window.viewport = ModuLearnFlowViewport.mount({
            modal:document.querySelector('#modal'), shell:document.querySelector('#shell'),
            map:document.querySelector('#map'), redraw:()=>{} });
          mount();
        }''')
        self.shell = self.page.locator('#shell')

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def test_zoom_anchor_pan_and_no_content_changes(self):
        self.shell.evaluate('(e)=>{e.scrollLeft=500;e.scrollTop=200}')
        self.page.locator('[data-flow-zoom-in]').click()
        self.assertAlmostEqual(float(self.shell.get_attribute('data-zoom')), 1.2)
        self.assertAlmostEqual(self.shell.evaluate('(e)=>e.scrollLeft'), 660, delta=2)
        bounds = self.shell.bounding_box()
        self.page.mouse.move(bounds['x']+15, bounds['y']+15)
        self.page.mouse.down()
        self.page.mouse.move(bounds['x']+115, bounds['y']+15, steps=5)
        self.page.mouse.up()
        self.assertAlmostEqual(self.shell.evaluate('(e)=>e.scrollLeft'), 560, delta=2)
        expect(self.page.locator('#map button')).to_have_text('Activity')
        self.shell.focus()
        self.page.keyboard.press('0')
        expect(self.shell).to_have_attribute('data-zoom', '1')

    def test_fit_and_focus_bring_activity_into_view(self):
        self.page.locator('[data-flow-fit]').click()
        self.assertLess(float(self.shell.get_attribute('data-zoom')), .3)
        self.page.locator('[data-flow-focus-view]').click()
        node = self.page.locator('#map button').bounding_box()
        shell = self.shell.bounding_box()
        self.assertGreaterEqual(node['x'], shell['x'])
        self.assertLessEqual(node['x']+node['width'], shell['x']+shell['width'])
        self.assertGreaterEqual(node['y'], shell['y'])
        self.assertLessEqual(node['y']+node['height'], shell['y']+shell['height'])

    def test_view_survives_reopen_and_component_remount(self):
        self.page.locator('[data-flow-zoom-out]').click()
        self.shell.evaluate('(e)=>{e.scrollLeft=400;e.scrollTop=100;e.dispatchEvent(new Event("scroll"))}')
        before = self.shell.evaluate('(e)=>[e.dataset.zoom,e.scrollLeft,e.scrollTop]')
        self.page.evaluate('viewport.destroy(); mount()')
        self.assertEqual(self.shell.evaluate('(e)=>[e.dataset.zoom,e.scrollLeft,e.scrollTop]'), before)
        self.page.evaluate('document.querySelector("#modal").dispatchEvent(new Event("shown.bs.modal"))')
        self.assertEqual(self.shell.evaluate('(e)=>[e.dataset.zoom,e.scrollLeft,e.scrollTop]'), before)
        expect(self.page.locator('.cfg-flow-stage')).to_have_count(1)

    def test_keyboard_focus_stays_in_modal_and_returns_to_opener(self):
        self.page.locator('#outside').focus()
        self.page.evaluate('''() => {
          const modal=document.querySelector('#modal');
          modal.dispatchEvent(new Event('show.bs.modal'));
          modal.dispatchEvent(new Event('shown.bs.modal'));
          window.bootstrap={Modal:{getOrCreateInstance:()=>({hide:()=>modal.dispatchEvent(new Event('hidden.bs.modal'))})}};
        }''')
        expect(self.page.locator('[data-flow-search]')).to_be_focused()
        self.page.keyboard.press('Shift+Tab')
        expect(self.page.locator('#last')).to_be_focused()
        self.page.keyboard.press('Tab')
        expect(self.page.locator('[data-flow-search]')).to_be_focused()
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#outside')).to_be_focused()


if __name__ == '__main__':
    unittest.main()
