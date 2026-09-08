import json
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent.codex_hud_data import collect_omx


class OmxScopeTests(unittest.TestCase):
    def test_missing_and_wrong_cwd_are_unavailable(self) -> None:
        cwd = pathlib.Path("/workspace")
        for session in ({"session_id": "bound"}, {"session_id": "bound", "cwd": "/other"}):
            with self.subTest(session=session):
                result = subprocess.CompletedProcess(["omx"], 0, json.dumps({"session": session, "team": {}}))
                with patch("agent.codex_hud_data.subprocess.run", return_value=result) as run:
                    self.assertEqual(collect_omx("bound", cwd).status, "unavailable")
                    self.assertEqual(run.call_args.kwargs["cwd"], cwd)

    def test_exact_session_and_cwd_are_accepted(self) -> None:
        payload = {"session": {"session_id": "bound", "cwd": "/workspace"}, "team": {}}
        result = subprocess.CompletedProcess(["omx"], 0, json.dumps(payload))
        with patch("agent.codex_hud_data.subprocess.run", return_value=result):
            self.assertEqual(collect_omx("bound", pathlib.Path("/workspace")).status, "active")


if __name__ == "__main__":
    unittest.main()
