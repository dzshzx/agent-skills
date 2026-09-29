from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_repository  # noqa: E402


class FrontmatterTest(unittest.TestCase):
    def parse(self, text: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SKILL.md"
            path.write_text(text, encoding="utf-8")
            return validate_repository.frontmatter(path)

    def test_quoted_values_are_unquoted(self):
        fields = self.parse(
            "---\nname: \"demo-skill\"\ndescription: 'Use when: a colon, #hash'\n---\nbody\n"
        )
        self.assertEqual(fields["name"], "demo-skill")
        self.assertEqual(fields["description"], "Use when: a colon, #hash")

    def test_folded_and_literal_scalars_keep_their_text(self):
        fields = self.parse(
            "---\nname: demo\ndescription: >-\n  First line\n  second line.\n"
            "notes: |\n  keep\n  this\n---\n"
        )
        self.assertEqual(fields["description"], "First line second line.")
        self.assertEqual(fields["notes"], "keep this")

    def test_malformed_frontmatter_is_rejected(self):
        for text, message in (
            ("name: demo\n", "must start"),
            ("---\nname: demo\n", "closing delimiter"),
            ("---\nname: [unclosed\n---\n", "invalid YAML"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, message):
                    self.parse(text)


if __name__ == "__main__":
    unittest.main()
