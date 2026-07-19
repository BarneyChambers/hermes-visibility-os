import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def load_config():
    hermes_constants = types.ModuleType("hermes_constants")
    hermes_constants.get_hermes_home = lambda: "."
    sys.modules["hermes_constants"] = hermes_constants
    module = importlib.import_module("plugins.visibility_os.core.config")
    return importlib.reload(module)


class VisibilityConfigProfileTest(unittest.TestCase):
    def test_profile_switch_reads_the_current_env_file(self):
        config = load_config()
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            Path(first, ".env").write_text("VISIBILITY_OS_COMPANY_NAME=First\n")
            Path(second, ".env").write_text("VISIBILITY_OS_COMPANY_NAME=Second\n")
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(config, "get_hermes_home", return_value=first):
                    self.assertEqual(
                        config.env_value("VISIBILITY_OS_COMPANY_NAME"),
                        "First",
                    )
                with patch.object(config, "get_hermes_home", return_value=second):
                    self.assertEqual(
                        config.env_value("VISIBILITY_OS_COMPANY_NAME"),
                        "Second",
                    )


if __name__ == "__main__":
    unittest.main()
