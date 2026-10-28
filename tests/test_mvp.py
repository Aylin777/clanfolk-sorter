import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import cli
import database
import models


ROOT = Path(__file__).resolve().parents[1]


class ModelTests(unittest.TestCase):
    def test_names(self):
        for factory, limit in ((models.Skill, 20), (lambda name: models.Character(name, 1, 2), 50)):
            for name in ("", " \t\n", "x" * (limit + 1)):
                with self.subTest(name=name, limit=limit), self.assertRaises(ValueError):
                    factory(name)
            self.assertEqual(factory("  Aila  ").name, "Aila")
            self.assertEqual(factory("x" * limit).name, "x" * limit)

    def test_preferences(self):
        with self.assertRaises(ValueError):
            models.Character("Aila", 1, 1)

    def test_levels(self):
        for aptitude, maximum in models.SkillRelation.APTITUDE_MAP.items():
            for level in (0, maximum):
                relation = models.SkillRelation(1, 1, level, aptitude)
                self.assertEqual(relation.max_lvl, maximum)
            for level in (-1, maximum + 1, 1.5):
                with self.subTest(level=level, aptitude=aptitude), self.assertRaises(ValueError):
                    models.SkillRelation(1, 1, level, aptitude)
        for aptitude in (-1, 5, 2.5, True):
            with self.assertRaises(ValueError):
                models.SkillRelation(1, 1, 0, aptitude)
        with self.assertRaises(ValueError):
            models.SkillRelation(1, 1, 0, 2, max_lvl=15)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "clanfolksorter.db"
        self.engine = create_engine(f"sqlite+pysqlite:///{self.path}")
        self.addCleanup(self.engine.dispose)
        self.engine_patch = patch.object(database, "engine", self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        database.init_db()
        database.add_skill("Farming")
        database.add_skill("Mining")
        database.add_char("Aila", 1, 2)

    def invoke(self, args, inputs=None):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), patch("builtins.input", side_effect=inputs) as prompt:
            code = cli.main(args)
        return code, stderr.getvalue(), prompt

    def test_noninteractive_and_rankings(self):
        code, error, prompt = self.invoke(["rel", "add", "1", "1", "5", "2"])
        self.assertEqual((code, error), (0, ""))
        prompt.assert_not_called()
        database.update_relation(1, 1, current_lvl=6)
        self.assertEqual(self.invoke(["folk", "sort", "1"])[0], 0)
        self.assertEqual(self.invoke(["clan", "status"])[0], 0)
        with Session(self.engine) as session:
            self.assertEqual(session.get(models.SkillRelation, (1, 1)).current_lvl, 6)

    def test_folk_without_recorded_skills(self):
        self.output.truncate(0)
        self.output.seek(0)
        code, error, _ = self.invoke(["folk", "sort", "1"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Aila has no recorded skills", self.output.getvalue())
        self.assertIn("rel add 1 --interactive", self.output.getvalue())
        self.assertNotIn("PRIORITY", self.output.getvalue())

    def test_clan_without_eligible_candidates(self):
        for state in ("no_records", "hated_only", "no_folks"):
            with self.subTest(state=state):
                if state == "hated_only":
                    database.add_relation(1, 2, 5, 2)
                if state == "no_folks":
                    with self.engine.begin() as connection:
                        connection.execute(database.relations.delete())
                        connection.execute(database.characters.delete())
                self.output.truncate(0)
                self.output.seek(0)
                code, error, _ = self.invoke(["clan", "status"])
                self.assertEqual((code, error), (0, ""))
                self.assertIn("No eligible candidates in the clan", self.output.getvalue())
                self.assertIn("hated skills are excluded", self.output.getvalue())

    def test_partial_clan_rankings_explain_missing_candidates(self):
        database.add_relation(1, 1, 0, 2)
        code, error, _ = self.invoke(["clan", "status"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("FARMING:", self.output.getvalue())
        self.assertIn("MINING:", self.output.getvalue())
        self.assertIn("No eligible candidates: this skill", self.output.getvalue())
        self.assertIn("Aila", self.output.getvalue())

    def test_skipping_creates_no_records_and_preserves_existing(self):
        database.add_relation(1, 1, 0, 2)
        code, error, _ = self.invoke(["rel", "add", "1", "--interactive"], ["", ""])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Unrecorded skills are excluded", self.output.getvalue())
        char, records = database.get_folk_priority_data(1)
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0][0].current_lvl, records[0][1]), (0, "Farming"))
        matrix = cli.sorter.get_global_assignment(database.get_global_priority_data())
        self.assertEqual(set(matrix), {"Farming"})

    def test_updates_reject_unchanged_values(self):
        database.add_relation(1, 1, 0, 2)
        for args in (
            ["skill", "update", "1", " Farming "],
            ["folk", "update", "1", "--name", " Aila ", "--loved", "1", "--hated", "2"],
            ["rel", "update", "1", "1", "--level", "0", "--aptitude", "2"],
        ):
            with self.subTest(args=args):
                code, error, _ = self.invoke(args)
                self.assertEqual(code, 1)
                self.assertIn("No changes", error)
        self.assertEqual(self.invoke(["folk", "update", "1", "--name", "Aila", "--loved", "2", "--hated", "1"])[0], 0)

    def test_interactive_skip_and_retry(self):
        code, error, prompt = self.invoke(["rel", "add", "1", "--interactive"], ["5", "9", "2", ""])
        self.assertEqual(code, 0)
        self.assertIn("between 0 and 4", error)
        self.assertEqual(prompt.call_count, 4)
        with Session(self.engine) as session:
            self.assertEqual(session.query(models.SkillRelation).count(), 1)

    def test_argument_combinations(self):
        for args in (["rel", "add", "1"], ["rel", "add", "1", "1", "5"],
                     ["rel", "add", "1", "1", "5", "2", "--interactive"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    cli.main(args)
                self.assertEqual(result.exception.code, 2)

    def test_missing_folk_before_prompt(self):
        code, error, prompt = self.invoke(["rel", "add", "999", "--interactive"])
        self.assertEqual(code, 1)
        self.assertIn("No folk", error)
        prompt.assert_not_called()

    def test_cancel_and_eof_preserve_entries(self):
        for interruption, expected_code in ((KeyboardInterrupt(), 130), (EOFError(), 1)):
            with self.subTest(interruption=type(interruption).__name__):
                with self.engine.begin() as connection:
                    connection.execute(database.relations.delete())
                code, error, _ = self.invoke(["rel", "add", "1", "--interactive"], ["5", "2", interruption])
                self.assertEqual(code, expected_code)
                self.assertIn("retained", error)
                self.assertNotIn("Traceback", error)
                with Session(self.engine) as session:
                    self.assertEqual(session.query(models.SkillRelation).count(), 1)

    def test_invalid_updates_leave_original_unchanged(self):
        database.add_relation(1, 1, 10, 2)
        invalid_actions = [
            lambda: database.update_skill(1, " "),
            lambda: database.update_skill(1, "x" * 21),
            lambda: database.update_skill(1, "Mining"),
            lambda: database.update_char(1, name=" "),
            lambda: database.update_char(1, name="x" * 51),
            lambda: database.update_char(1, loved_id=2),
            lambda: database.update_char(1, hated_id=999),
            lambda: database.update_relation(1, 1, current_lvl=-1),
            lambda: database.update_relation(1, 1, aptitude=5),
            lambda: database.update_relation(1, 1, aptitude=0),
        ]
        for action in invalid_actions:
            with self.assertRaises(ValueError):
                action()
        with Session(self.engine) as session:
            self.assertEqual(session.get(models.Skill, 1).name, "Farming")
            char = session.get(models.Character, 1)
            self.assertEqual((char.name, char.loved_id, char.hated_id), ("Aila", 1, 2))
            relation = session.get(models.SkillRelation, (1, 1))
            self.assertEqual((relation.current_lvl, relation.aptitude), (10, 2))
        database.update_relation(1, 1, current_lvl=5, aptitude=0)

    def test_user_errors_have_nonzero_status(self):
        database.add_relation(1, 1, 1, 2)
        for args, message in (
            (["skill", "add", "Farming"], "already exists"),
            (["folk", "add", "New", "1", "999"], "No skill"),
            (["folk", "sort", "999"], "No folk"),
            (["rel", "add", "1", "1", "1", "2"], "already has"),
            (["rel", "add", "1", "999", "1", "2"], "No skill"),
            (["rel", "add", "1", "2", "99", "2"], "Level"),
            (["folk", "update", "1"], "at least one"),
            (["rel", "update", "1", "1"], "level or aptitude"),
        ):
            with self.subTest(args=args):
                code, error, _ = self.invoke(args)
                self.assertEqual(code, 1)
                self.assertIn(message, error)
                self.assertNotIn("Traceback", error)

    def test_database_constraints_on_direct_writes(self):
        statements = [
            "INSERT INTO skills VALUES (3, 'Farming', 1)",
            "INSERT INTO skills VALUES (3, '', 1)",
            "INSERT INTO characters VALUES (2, 'B', 1, 1, 1)",
            "INSERT INTO characters VALUES (2, 'B', 1, 999, 1)",
            "INSERT INTO relations VALUES (999, 1, 1, 2, 12, 1)",
            "INSERT INTO relations VALUES (1, 1, -1, 2, 12, 1)",
            "INSERT INTO relations VALUES (1, 1, 13, 2, 12, 1)",
            "INSERT INTO relations VALUES (1, 1, 1, 5, 5, 1)",
            "INSERT INTO relations VALUES (1, 1, 1, 2, 15, 1)",
        ]
        for statement in statements:
            with self.subTest(statement=statement), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.exec_driver_sql(statement)
        for _ in range(2):
            self.engine.dispose()
            with self.engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)

    def make_legacy(self, duplicate=False, orphan=False):
        self.engine.dispose()
        self.path.unlink()
        with sqlite3.connect(self.path) as connection:
            connection.executescript("""
                CREATE TABLE skills (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT NOT NULL, loved_id INTEGER NOT NULL REFERENCES skills(id), hated_id INTEGER NOT NULL REFERENCES skills(id), created_at INTEGER NOT NULL);
                CREATE TABLE relations (character_id INTEGER REFERENCES characters(id), skill_id INTEGER REFERENCES skills(id), current_lvl INTEGER NOT NULL, aptitude INTEGER NOT NULL, max_lvl INTEGER NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(character_id, skill_id));
                INSERT INTO skills VALUES (1, ' Farming ', 1), (2, 'Mining', 1);
                INSERT INTO characters VALUES (1, 'Aila', 1, 2, 1);
                INSERT INTO relations VALUES (1, 1, 5, 2, 12, 1);
            """)
            if duplicate:
                connection.execute("INSERT INTO skills VALUES (3, 'Farming', 1)")
            if orphan:
                connection.execute("UPDATE characters SET hated_id=999")

    def test_migrate_preserves_data_and_backup(self):
        self.make_legacy()
        original = self.path.read_bytes()
        database.migrate_db()
        database.ensure_initialized()
        self.assertEqual(database.get_all_skills()[0].name, "Farming")
        self.assertEqual(database.get_folk_priority_data(1)[0].name, "Aila")
        backups = list(self.path.parent.glob("*.backup-*.db"))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as backup:
            self.assertEqual(backup.execute("SELECT name FROM skills WHERE id=1").fetchone()[0], " Farming ")
        database.migrate_db()
        self.assertEqual(len(list(self.path.parent.glob("*.backup-*.db"))), 1)
        self.assertTrue(original)

    def test_migration_rolls_back_duplicate_and_orphan(self):
        for options, message in (({"duplicate": True}, "already exists"), ({"orphan": True}, "Referenced")):
            with self.subTest(options=options):
                self.make_legacy(**options)
                with sqlite3.connect(self.path) as connection:
                    before = list(connection.iterdump())
                code, error, _ = self.invoke(["migrate"])
                self.assertEqual(code, 1)
                self.assertIn(message, error)
                with sqlite3.connect(self.path) as connection:
                    self.assertEqual(list(connection.iterdump()), before)
                    self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_legacy_commands_require_explicit_migration(self):
        self.make_legacy()
        for args in (["init"], ["skill", "list"]):
            code, error, _ = self.invoke(args)
            self.assertEqual(code, 1)
            self.assertIn("migrate", error)

    def test_invalid_legacy_level_is_not_silently_clamped(self):
        self.make_legacy()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE relations SET current_lvl=99")
        code, error, _ = self.invoke(["migrate"])
        self.assertEqual(code, 1)
        self.assertIn("Level", error)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT current_lvl FROM relations").fetchone()[0], 99)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_unexpected_errors_are_logged_and_fail(self):
        with patch.object(database, "get_all_skills", side_effect=RuntimeError("unexpected")):
            with self.assertLogs(level="ERROR") as logs:
                code, _, _ = self.invoke(["skill", "list"])
        self.assertEqual(code, 1)
        self.assertIn("unexpected", "\n".join(logs.output))


class ProcessTests(unittest.TestCase):
    def copy_application(self, directory):
        repo = Path(directory) / "cloned_repo"
        repo.mkdir()
        for name in ("cli.py", "database.py", "models.py", "sorter.py"):
            shutil.copy2(ROOT / name, repo / name)
        return repo

    def test_fresh_database_workflow_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.copy_application(directory)
            def run(*args):
                return subprocess.run([sys.executable, "-B", str(repo / "cli.py"), *args],
                                      cwd=directory, input="", capture_output=True, text=True, timeout=20)
            result = run("skill", "list")
            self.assertEqual(result.returncode, 1)
            self.assertIn("init", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            for args in (("init",), ("init",), ("skill", "add", "Farming"),
                         ("skill", "add", "Mining"), ("folk", "add", "Aila", "1", "2"),
                         ("rel", "add", "1", "1", "5", "2"),
                         ("folk", "sort", "1"), ("clan", "status")):
                result = run(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Aila", result.stdout)
            self.assertTrue((repo / "clanfolksorter.db").is_file())
            self.assertFalse((Path(directory) / "clanfolksorter.db").exists())
            self.assertEqual(run("rel", "add", "1").returncode, 2)
            result = run("rel", "add", "1", "--interactive")
            self.assertEqual(result.returncode, 1)
            self.assertIn("Input ended", result.stderr)

    def test_personal_database_migration_on_copy(self):
        personal = ROOT / "clanfolksorter.db"
        if not personal.exists():
            self.skipTest("No personal legacy database available")
        before = hashlib.sha256(personal.read_bytes()).digest()
        with tempfile.TemporaryDirectory() as directory:
            repo = self.copy_application(directory)
            target = repo / personal.name
            with sqlite3.connect(f"{personal.as_uri()}?mode=ro", uri=True) as source:
                with sqlite3.connect(target) as destination:
                    source.backup(destination)
            result = subprocess.run([sys.executable, "-B", str(repo / "cli.py"), "migrate"],
                                    cwd=directory, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            with sqlite3.connect(target) as connection:
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(hashlib.sha256(personal.read_bytes()).digest(), before)


if __name__ == "__main__":
    unittest.main()