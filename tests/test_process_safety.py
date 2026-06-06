import importlib
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTENDS = ROOT / "frontends"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FRONTENDS) not in sys.path:
    sys.path.insert(0, str(FRONTENDS))

ga = importlib.import_module("ga")
slash_cmds = importlib.import_module("slash_cmds")


class CodeRunSafetyTests(unittest.TestCase):
    def test_blocks_python_os_exit(self):
        reason = ga._unsafe_code_run_reason("import os\nos._exit(0)", "python")

        self.assertIsNotNone(reason)

    def test_blocks_python_dynamic_os_exit(self):
        reason = ga._unsafe_code_run_reason('import os\ngetattr(os, "_" + "exit")(0)', "python")

        self.assertIsNotNone(reason)

    def test_blocks_python_parent_process_kill(self):
        reason = ga._unsafe_code_run_reason("import os\nos.kill(os.getppid(), 9)", "python")

        self.assertIsNotNone(reason)

    def test_blocks_python_eval_embedded_exit(self):
        reason = ga._unsafe_code_run_reason('eval("os._exit(0)")', "python")

        self.assertIsNotNone(reason)

    def test_blocks_broad_python_taskkill(self):
        reason = ga._unsafe_code_run_reason("taskkill /IM python.exe /F", "powershell")

        self.assertIsNotNone(reason)

    def test_blocks_python_subprocess_taskkill(self):
        code = 'import subprocess\nsubprocess.run(["taskkill", "/IM", "python.exe", "/F"])'
        reason = ga._unsafe_code_run_reason(code, "python")

        self.assertIsNotNone(reason)

    def test_blocks_powershell_remove_item(self):
        reason = ga._unsafe_code_run_reason('Remove-Item -LiteralPath ".\\docs" -Recurse', "powershell")

        self.assertIsNotNone(reason)

    def test_blocks_git_reset_hard(self):
        reason = ga._unsafe_code_run_reason("git reset --hard HEAD", "powershell")

        self.assertIsNotNone(reason)

    def test_blocks_git_clean_force(self):
        reason = ga._unsafe_code_run_reason("git clean -fdx", "bash")

        self.assertIsNotNone(reason)

    def test_blocks_find_delete(self):
        reason = ga._unsafe_code_run_reason("find . -name '*.tmp' -delete", "bash")

        self.assertIsNotNone(reason)

    def test_blocks_python_shutil_rmtree(self):
        reason = ga._unsafe_code_run_reason('import shutil\nshutil.rmtree("docs")', "python")

        self.assertIsNotNone(reason)

    def test_blocks_python_path_unlink(self):
        reason = ga._unsafe_code_run_reason('from pathlib import Path\nPath("mykey.py").unlink()', "python")

        self.assertIsNotNone(reason)

    def test_allows_normal_python_script(self):
        reason = ga._unsafe_code_run_reason("print('hello')", "python")

        self.assertIsNone(reason)

    def test_comment_does_not_trigger_python_block(self):
        reason = ga._unsafe_code_run_reason("# os._exit(0)\nprint('safe')", "python")

        self.assertIsNone(reason)


class ServiceProcessMatchTests(unittest.TestCase):
    def test_reflect_service_matches_this_repo_cwd(self):
        svc = {"name": "reflect/foo.py", "kind": "reflect"}
        cmd = [sys.executable, "agentmain.py", "--reflect", "reflect/foo.py"]

        self.assertTrue(slash_cmds._match_service(cmd, svc, str(ROOT)))

    def test_reflect_service_rejects_other_checkout_cwd(self):
        svc = {"name": "reflect/foo.py", "kind": "reflect"}
        cmd = [sys.executable, "agentmain.py", "--reflect", "reflect/foo.py"]
        other_checkout = ROOT.parent / "OtherGenericAgent"

        self.assertFalse(slash_cmds._match_service(cmd, svc, str(other_checkout)))

    def test_direct_reflect_script_matches_this_repo(self):
        svc = {"name": "reflect/foo.py", "kind": "reflect"}
        cmd = [sys.executable, str(ROOT / "reflect" / "foo.py")]

        self.assertTrue(slash_cmds._match_service(cmd, svc, str(ROOT)))

    def test_current_process_family_returns_false_when_uninspectable(self):
        class BrokenProcess:
            @property
            def pid(self):
                raise RuntimeError("inaccessible")

        self.assertFalse(slash_cmds._is_current_process_family(BrokenProcess()))


if __name__ == "__main__":
    unittest.main()
