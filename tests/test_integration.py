import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from control import Controller, atomic_json

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='omavoid home ')
        self.addCleanup(self.tmp.cleanup)
        self.c=Controller(Path(self.tmp.name))
        c=self.c
        (c.root/'game').mkdir(parents=True)
        (c.root/'game/fringe.py').write_text('# test game')
        clone=c.plugins/'tester.idle';clone.mkdir()
        atomic_json(clone/'manifest.json',{'id':'tester.idle','omarchy':{'clonedFrom':'omarchy.idle'}})
        self.original='    runProcess(screensaverProcess, "screensaver", "[[ $(omarchy-shell lock isLocked 2>/dev/null) == \\"true\\" ]] || omarchy-launch-screensaver")'
        self.service=clone/'Service.qml'
        self.service.write_text('before\n'+self.original+'\nafter\n')
        atomic_json(c.shell_config,{'plugins':[{'id':'tester.idle'}], 'idle':{'screensaver':150,'lock':300}})

    def test_toggle_restore_and_idempotence(self):
        c=self.c;prior=c.shell_config.read_bytes()
        c.choose('omavoid');c.choose('stock');c.choose('omavoid')
        self.assertEqual(c.mode(),'omavoid')
        self.assertEqual(c.shell_config.read_bytes(),prior)
        self.assertIn('else omarchy-launch-screensaver',self.service.read_text())
        self.service.write_text(self.service.read_text()+'// unrelated later edit\n')
        c.restore()
        self.assertIn(self.original,self.service.read_text())
        self.assertIn('// unrelated later edit',self.service.read_text())
        self.assertEqual(c.mode(),'stock')

    def test_corrupt_selection_falls_back_to_stock(self):
        self.c.config.parent.mkdir(parents=True)
        self.c.config.write_text('{bad')
        self.assertEqual(self.c.mode(),'stock')

    def test_unknown_custom_launch_is_preserved(self):
        self.service.write_text(self.service.read_text().replace('omarchy-launch-screensaver','custom-saver'))
        old=self.service.read_bytes()
        with self.assertRaises(RuntimeError): self.c.integrate()
        self.assertEqual(self.service.read_bytes(),old)

    def test_user_edits_after_install_not_overwritten(self):
        self.c.integrate()
        self.service.write_text('custom replacement')
        with self.assertRaises(RuntimeError): self.c.restore()
        self.assertEqual(self.service.read_text(),'custom replacement')
        self.assertTrue(self.c.state.exists())

    def test_commands_are_arguments_not_shell_strings(self):
        self.assertEqual(self.c.command('stock'),['omarchy-launch-screensaver','force'])
        self.assertEqual(self.c.command('omavoid')[1],str(self.c.root/'bin/omavoid'))
        self.assertIn(' ',str(self.c.root))

if __name__=='__main__': unittest.main()
