"""The CTO's safety check: what it lets into drafts/ and what it stops.

    python3 -m unittest discover tests
"""
import unittest

import io
import os
import tempfile
from pathlib import Path
from unittest import mock

from agents.cto import run as cto
from agents.cto.run import check
from core import journal, llm

OK_RUN = "from core import env\n\ndef main():\n    env.load()\n"


def plan(files, name="new_helper"):
    return {"name": name, "files": [{"path": p, "content": c} for p, c in files]}


class CheckTest(unittest.TestCase):
    def test_good_draft_passes(self):
        self.assertEqual(check(plan([("agents/new_helper/run.py", OK_RUN)])), [])

    def test_file_outside_its_folder_is_stopped(self):
        problems = check(plan([("agents/new_helper/run.py", OK_RUN), ("core/llm.py", "x = 1\n")]))
        self.assertTrue(any("вне папки" in p for p in problems))

    def test_path_escape_is_stopped(self):
        problems = check(plan([("agents/new_helper/../../.env", "x\n"), ("agents/new_helper/run.py", OK_RUN)]))
        self.assertTrue(any("вне папки" in p for p in problems))

    def test_foreign_package_is_stopped(self):
        problems = check(plan([("agents/new_helper/run.py", "import requests\n")]))
        self.assertTrue(any("requests" in p for p in problems))

    def test_shell_access_is_stopped(self):
        problems = check(plan([("agents/new_helper/run.py", "import subprocess\nimport shutil\n")]))
        self.assertEqual(len([p for p in problems if "запрещённый модуль" in p]), 2)

    def test_os_is_stopped(self):
        problems = check(plan([("agents/new_helper/run.py", "import os\nos.system('ls')\n")]))
        self.assertTrue(any("запрещённый модуль os" in p for p in problems))

    def test_deleting_files_is_stopped(self):
        code = "from pathlib import Path\nPath('company/journal.md').unlink()\n"
        problems = check(plan([("agents/new_helper/run.py", code)]))
        self.assertTrue(any("unlink" in p for p in problems))

    def test_eval_is_stopped(self):
        problems = check(plan([("agents/new_helper/run.py", "eval('1+1')\n")]))
        self.assertTrue(any("eval" in p for p in problems))

    def test_syntax_error_is_stopped(self):
        problems = check(plan([("agents/new_helper/run.py", "def main(:\n")]))
        self.assertTrue(any("ошибка в коде" in p for p in problems))

    def test_existing_agent_is_not_overwritten(self):
        problems = check(plan([("agents/secretary/run.py", OK_RUN)], name="secretary"))
        self.assertTrue(any("уже есть" in p for p in problems))

    def test_draft_without_run_py_is_stopped(self):
        self.assertIn("нет run.py", check(plan([("agents/new_helper/prompt.ru.md", "текст")])))


class DraftTest(unittest.TestCase):
    """The model is faked; the CTO's handling of its answer is real."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for p in [mock.patch.object(cto, "DRAFTS", Path(self.tmp.name) / "drafts"),
                  mock.patch.object(journal, "JOURNAL", Path(self.tmp.name) / "journal.md"),
                  mock.patch("sys.stdout", io.StringIO())]:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_not_json_answer_makes_no_draft(self):
        with mock.patch.object(llm, "chat", lambda *a, **k: "Конечно! Вот агент:"):
            cto.draft("сделай агента")
        self.assertFalse(cto.DRAFTS.exists())

    def test_good_answer_is_saved_as_a_draft_and_not_run(self):
        answer = '{"name": "evening_note", "title": "Заметка", "summary": "пишет заметку", "files": [{"path": "agents/evening_note/run.py", "content": "raise SystemExit(\\"must not run\\")\\n"}], "run": "", "needs_owner_yes": []}'
        with mock.patch.object(llm, "chat", lambda *a, **k: answer):
            cto.draft("сделай агента")
        self.assertTrue((cto.DRAFTS / "evening_note" / "run.py").exists())
        self.assertIn("написал черновик", journal.JOURNAL.read_text())

    def test_dangerous_answer_is_not_saved(self):
        answer = '{"name": "cleaner", "title": "x", "summary": "x", "files": [{"path": "agents/cleaner/run.py", "content": "import shutil\\nshutil.rmtree(\\"company\\")\\n"}]}'
        with mock.patch.object(llm, "chat", lambda *a, **k: answer):
            cto.draft("сделай агента")
        self.assertFalse((cto.DRAFTS / "cleaner").exists())


if __name__ == "__main__":
    unittest.main()
