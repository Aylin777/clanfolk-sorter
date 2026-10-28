import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Column, ForeignKey, Integer, MetaData, Table, Text,
    create_engine, event, inspect,
)
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, aliased, registry

import models


@event.listens_for(Engine, "connect")
def enable_foreign_keys(connection, connection_record):
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")


DB_PATH = Path(__file__).resolve().parent / "clanfolksorter.db"
engine = create_engine(URL.create("sqlite+pysqlite", database=str(DB_PATH)))
metadata = MetaData()

skills = Table(
    "skills", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("created_at", Integer, nullable=False),
    CheckConstraint("length(trim(name)) BETWEEN 1 AND 20 AND name = trim(name)", name="skill_name_valid"),
)
characters = Table(
    "characters", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("loved_id", ForeignKey("skills.id"), nullable=False),
    Column("hated_id", ForeignKey("skills.id"), nullable=False),
    Column("created_at", Integer, nullable=False),
    CheckConstraint("length(trim(name)) BETWEEN 1 AND 50 AND name = trim(name)", name="folk_name_valid"),
    CheckConstraint("loved_id != hated_id", name="distinct_preferences"),
)
relations = Table(
    "relations", metadata,
    Column("character_id", ForeignKey("characters.id"), primary_key=True),
    Column("skill_id", ForeignKey("skills.id"), primary_key=True),
    Column("current_lvl", Integer, nullable=False),
    Column("aptitude", Integer, nullable=False),
    Column("max_lvl", Integer, nullable=False),
    Column("created_at", Integer, nullable=False),
    CheckConstraint("typeof(aptitude) = 'integer' AND aptitude BETWEEN 0 AND 4", name="aptitude_valid"),
    CheckConstraint("typeof(current_lvl) = 'integer' AND current_lvl BETWEEN 0 AND max_lvl", name="level_valid"),
    CheckConstraint("max_lvl = CASE aptitude WHEN 0 THEN 5 WHEN 1 THEN 10 WHEN 2 THEN 12 WHEN 3 THEN 14 WHEN 4 THEN 15 END", name="max_level_valid"),
)

mapper_registry = registry()
mapper_registry.map_imperatively(models.Skill, skills)
mapper_registry.map_imperatively(models.Character, characters)
mapper_registry.map_imperatively(models.SkillRelation, relations)


def ensure_initialized():
    if not set(metadata.tables).issubset(inspect(engine).get_table_names()):
        raise ValueError("Database is not initialized. Run 'python cli.py init' first.")
    with engine.connect() as connection:
        if connection.exec_driver_sql("PRAGMA user_version").scalar() != 1:
            raise ValueError("Database schema needs upgrading. Run 'python cli.py migrate'.")


def init_db():
    if set(metadata.tables).intersection(inspect(engine).get_table_names()):
        ensure_initialized()
    else:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.exec_driver_sql("PRAGMA user_version=1")
    print("Database initialized and tables created.")


def migrate_db():
    """Back up and rebuild the original schema with current constraints."""
    if not set(metadata.tables).issubset(inspect(engine).get_table_names()):
        raise ValueError("Database is not initialized. Run 'python cli.py init' first.")
    with engine.connect() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar()
    if version == 1:
        print("Database schema is already current.")
        return
    if version != 0:
        raise ValueError(f"Unsupported database schema version: {version}.")
    path = Path(engine.url.database).resolve()
    backup = path.with_name(f"{path.stem}.backup-{uuid4().hex}.db")
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as source:
        with sqlite3.connect(backup) as destination:
            source.backup(destination)
    print(f"Backup saved to {backup}")
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            rows = {table.name: [dict(row) for row in connection.execute(table.select()).mappings()]
                    for table in metadata.sorted_tables}
            for row in rows["skills"]:
                row["name"] = models.Skill(**row).name
            for row in rows["characters"]:
                row["name"] = models.Character(**row).name
            for row in rows["relations"]:
                models.SkillRelation(**row)
            for table in reversed(metadata.sorted_tables):
                table.drop(connection)
            metadata.create_all(connection)
            for table in metadata.sorted_tables:
                if rows[table.name]:
                    connection.execute(table.insert(), rows[table.name])
            connection.exec_driver_sql("PRAGMA user_version=1")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    print("Database migrated successfully.")


def require_record(session, model, identifier, label):
    record = session.get(model, identifier)
    if record is None:
        raise ValueError(f"No {label} found with ID {identifier}.")
    return record


def get_char(char_id):
    with Session(engine) as session:
        return require_record(session, models.Character, char_id, "folk")


def check_skill_name(session, name, exclude_id=None):
    query = session.query(models.Skill).filter(models.Skill.name == name)
    if exclude_id is not None:
        query = query.filter(models.Skill.id != exclude_id)
    if query.first() is not None:
        raise ValueError(f"A skill named '{name}' already exists.")


def add_skill(skill_name):
    skill = models.Skill(name=skill_name, created_at=int(time.time()))
    with Session(engine) as session:
        check_skill_name(session, skill.name)
        session.add(skill)
        session.commit()
        print(f"Saved: {skill}")


def get_all_skills():
    with Session(engine) as session:
        return session.query(models.Skill).order_by(models.Skill.name).all()


def update_skill(skill_id, new_name):
    name = models.Skill(new_name).name
    with Session(engine) as session:
        skill = require_record(session, models.Skill, skill_id, "skill")
        if skill.name == name:
            raise ValueError("No changes: skill name already matches the stored value.")
        check_skill_name(session, name, skill_id)
        skill.name = name
        session.commit()
        print(f"Skill {skill_id} updated to '{name}'.")


def add_char(char_name, loved_id, hated_id):
    char = models.Character(char_name, loved_id, hated_id, created_at=int(time.time()))
    with Session(engine) as session:
        require_record(session, models.Skill, loved_id, "skill")
        require_record(session, models.Skill, hated_id, "skill")
        session.add(char)
        session.commit()
        print(f"Character {char.name} was saved with ID {char.id}")


def get_all_chars():
    with Session(engine) as session:
        loved_skill = aliased(models.Skill)
        hated_skill = aliased(models.Skill)
        return session.query(models.Character, loved_skill.name, hated_skill.name).join(
            loved_skill, models.Character.loved_id == loved_skill.id
        ).join(hated_skill, models.Character.hated_id == hated_skill.id).order_by(models.Character.id).all()


def update_char(char_id, name=None, loved_id=None, hated_id=None):
    if name is None and loved_id is None and hated_id is None:
        raise ValueError("Supply at least one folk field to update.")
    with Session(engine) as session:
        char = require_record(session, models.Character, char_id, "folk")
        validated = models.Character(
            char.name if name is None else name,
            char.loved_id if loved_id is None else loved_id,
            char.hated_id if hated_id is None else hated_id,
        )
        require_record(session, models.Skill, validated.loved_id, "skill")
        require_record(session, models.Skill, validated.hated_id, "skill")
        if (char.name, char.loved_id, char.hated_id) == (validated.name, validated.loved_id, validated.hated_id):
            raise ValueError("No changes: folk fields already match the stored values.")
        char.name, char.loved_id, char.hated_id = validated.name, validated.loved_id, validated.hated_id
        session.commit()
        print(f"Folk ID {char_id} updated successfully.")


def add_relation(char_id, skill_id, current_lvl, aptitude):
    relation = models.SkillRelation(char_id, skill_id, current_lvl, aptitude, created_at=int(time.time()))
    with Session(engine) as session:
        require_record(session, models.Character, char_id, "folk")
        require_record(session, models.Skill, skill_id, "skill")
        if session.get(models.SkillRelation, (char_id, skill_id)) is not None:
            raise ValueError("This folk already has a relation for this skill; use 'rel update'.")
        session.add(relation)
        session.commit()
        print(f"Relation added: {relation}")


def update_relation(char_id, skill_id, current_lvl=None, aptitude=None):
    if current_lvl is None and aptitude is None:
        raise ValueError("Supply a level or aptitude to update.")
    with Session(engine) as session:
        relation = require_record(session, models.SkillRelation, (char_id, skill_id), "relation")
        validated = models.SkillRelation(
            char_id, skill_id,
            relation.current_lvl if current_lvl is None else current_lvl,
            relation.aptitude if aptitude is None else aptitude,
        )
        if (relation.current_lvl, relation.aptitude, relation.max_lvl) == (validated.current_lvl, validated.aptitude, validated.max_lvl):
            raise ValueError("No changes: relation fields already match the stored values.")
        relation.current_lvl, relation.aptitude, relation.max_lvl = validated.current_lvl, validated.aptitude, validated.max_lvl
        session.commit()
        print(f"Updated {relation}")


def get_folk_priority_data(char_id):
    with Session(engine) as session:
        char = require_record(session, models.Character, char_id, "folk")
        results = session.query(models.SkillRelation, models.Skill.name).join(
            models.Skill, models.SkillRelation.skill_id == models.Skill.id
        ).filter(models.SkillRelation.character_id == char_id).all()
        return char, results


def get_global_priority_data():
    with Session(engine) as session:
        return session.query(models.Character, models.SkillRelation, models.Skill.name).join(
            models.SkillRelation, models.Character.id == models.SkillRelation.character_id
        ).join(models.Skill, models.SkillRelation.skill_id == models.Skill.id).all()