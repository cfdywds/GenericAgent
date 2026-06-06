import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ga_cli import cli


class CliMetadataTests(unittest.TestCase):
    def test_help_examples_have_registered_commands(self):
        for name in ("web", "pet"):
            self.assertIn(name, cli.COMMANDS)
            self.assertIsNotNone(cli.COMMANDS[name]["cmd"])

    def test_web_native_flag_switches_to_launch_shell(self):
        web = cli.COMMANDS["web"]

        self.assertIn("--native", web.get("flags", {}))
        self.assertIn("launch.pyw", " ".join(web["flags"]["--native"]["cmd"]))


if __name__ == "__main__":
    unittest.main()
