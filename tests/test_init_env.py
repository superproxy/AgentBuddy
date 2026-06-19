import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "init-env.py"
SPEC = importlib.util.spec_from_file_location("init_env", SCRIPT_PATH)
init_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(init_env)


class FlattenEnvConfigTests(unittest.TestCase):
    def test_vision_flat_provider_exports_default_model(self):
        env_config = {
            "vision": {
                "volcengine": {
                    "base_url": "https://example.invalid/api",
                    "api_key": "test-key",
                    "models": {
                        "doubao-seedance-2-0-fast-260128": {
                            "name": "Seedance fast"
                        }
                    },
                }
            }
        }

        flat = init_env.flatten_env_config(env_config, "", [])

        self.assertEqual(
            flat["VISION_VOLCENGINE_MODEL"],
            "doubao-seedance-2-0-fast-260128",
        )


if __name__ == "__main__":
    unittest.main()
