import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


REGISTERS = pathlib.Path(__file__).resolve().parents[2] / "fpga" / "registers"
sys.path.insert(0, str(REGISTERS))

import generate_register_map as generator


class RegisterGeneratorTests(unittest.TestCase):
    def test_authoritative_map_renders(self):
        outputs = generator.render()
        self.assertEqual(set(outputs), {generator.RTL, generator.PY, generator.MD})

    def test_overlapping_regions_are_rejected(self):
        spec = json.loads(generator.SPEC.read_text(encoding="utf-8"))
        altered = copy.deepcopy(spec)
        altered["regions"][1]["start"] = altered["regions"][0]["end"]
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "register_map.json"
            path.write_text(json.dumps(altered), encoding="utf-8")
            with mock.patch.object(generator, "SPEC", path):
                with self.assertRaisesRegex(ValueError, "region overlap"):
                    generator.render()


if __name__ == "__main__":
    unittest.main()
