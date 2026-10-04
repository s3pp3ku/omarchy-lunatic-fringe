import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'game'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from appearance import palette, preferences, TEAL
from control import Controller, atomic_json

class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.controller=Controller(self.home)

    def test_independent_defaults_and_choices(self):
        self.assertEqual(preferences(self.home),{'icon':'white','game':'teal'})
        self.controller.set_appearance('game','theme')
        self.assertEqual(preferences(self.home),{'icon':'white','game':'theme'})
        self.controller.set_appearance('icon','teal')
        self.assertEqual(preferences(self.home),{'icon':'teal','game':'theme'})
        self.assertEqual(self.controller.status()['appearance'],preferences(self.home))

    def test_current_theme_and_live_change(self):
        self.controller.set_appearance('game','theme')
        theme=self.home/'.local/state/omarchy/current/theme/colors.toml'
        theme.parent.mkdir(parents=True)
        theme.write_text('accent="#ff0080"\ncyan="#00aaff"\nyellow="#ffaa00"\n')
        first=palette(self.home)
        self.assertEqual(first['primary'],(1.,0.,128/255))
        theme.write_text('accent="#336699"\n')
        self.assertEqual(palette(self.home)['primary'],(.2,.4,.6))
        self.assertNotEqual(first,palette(self.home))

    def test_white_and_invalid_color_fallback(self):
        self.controller.set_appearance('game','white')
        self.assertEqual(palette(self.home)['primary'],(1.,1.,1.))
        self.controller.set_appearance('game','theme')
        theme=self.home/'.local/state/omarchy/current/theme/colors.toml'
        theme.parent.mkdir(parents=True)
        theme.write_text('accent="not a color"\n')
        self.assertEqual(palette(self.home)['primary'],TEAL)
        with self.assertRaises(ValueError):self.controller.set_appearance('game','unknown')

    def test_corrupt_settings_fallback(self):
        path=self.home/'.config/omavoid/appearance.json'
        path.parent.mkdir(parents=True);path.write_text('{bad')
        self.assertEqual(preferences(self.home)['icon'],'white')
        self.assertEqual(palette(self.home)['primary'],TEAL)

if __name__=='__main__':unittest.main()
