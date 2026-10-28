import argparse
import logging
import sys

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import database
import sorter


def run(argv=None):
    parser = argparse.ArgumentParser(prog='Clanfolk Skill Sorter', description='This will prioritize skills for a single folk - for now')
    subparsers = parser.add_subparsers(title= "Subcommands", dest="cmd", help="Available cmds to operate app")

    # CMDs
    # init
    parser_init = subparsers.add_parser('init', help="Initialize database")
    subparsers.add_parser('migrate', help="Back up and upgrade an existing database")

    # skill 
    parser_skill = subparsers.add_parser('skill', help="Skill management")
    skill_sub = parser_skill.add_subparsers(title="Skill CMDs", dest="skill_cmd")
    # skill add
    parser_skill_add = skill_sub.add_parser('add', help="Add a new skill")
    parser_skill_add.add_argument('name', type=str, help="Name of the skill")
    # skill list
    parser_skill_list = skill_sub.add_parser('list', help="Get all skills")
    # skill name update
    parser_skill_upd = skill_sub.add_parser('update', help="Rename a skill")
    parser_skill_upd.add_argument('id', type=int, help="ID of the skill to update")
    parser_skill_upd.add_argument('name', type=str, help="New name for the skill")
    
    # folk
    parser_folk = subparsers.add_parser('folk', help="Folk management")
    folk_sub = parser_folk.add_subparsers(title="Folk CMDs", dest="folk_cmd")
    # folk add
    parser_folk_add = folk_sub.add_parser('add', help="Add a new folk")
    parser_folk_add.add_argument('name', type=str, help="Name of the folk")
    parser_folk_add.add_argument('loved', type=int, help="ID of the loved skill")
    parser_folk_add.add_argument('hated', type=int, help="ID of the hated skill")
    # folk list
    parser_folk_list = folk_sub.add_parser('list', help="Get all folks")
    # folk update
    parser_folk_upd = folk_sub.add_parser('update', help="Update folk details")
    parser_folk_upd.add_argument('id', type=int, help="ID of the folk to update")
    parser_folk_upd.add_argument('--name', type=str, help="New name")
    parser_folk_upd.add_argument('--loved', type=int, help="New loved skill ID")
    parser_folk_upd.add_argument('--hated', type=int, help="New hated skill ID")
    # folk skill sort
    parser_folk_sort = folk_sub.add_parser('sort', help="Prioritise skills for a folk")
    parser_folk_sort.add_argument('id', type=int)


    # relation char-skill
    parser_rel = subparsers.add_parser('rel', help="Manage skill levels for a folk")
    rel_sub = parser_rel.add_subparsers(title="Relation CMDs", dest="rel_cmd")
    # relation add
    parser_rel_add = rel_sub.add_parser('add', help="Set a skill level for a folk")
    parser_rel_add.add_argument('char_id', type=int)
    parser_rel_add.add_argument('skill_id', type=int, nargs='?')
    parser_rel_add.add_argument('level', type=int, help="Current level", nargs='?')
    parser_rel_add.add_argument('aptitude', type=int, choices=[0, 1, 2, 3, 4], help="Aptitude (choose between 0-4)", nargs='?')
    parser_rel_add.add_argument('--interactive', action='store_true', help='Prompt for each skill')
    # relation update
    parser_rel_upd = rel_sub.add_parser('update', help="Update existing skill level")
    parser_rel_upd.add_argument('char_id', type=int)
    parser_rel_upd.add_argument('skill_id', type=int)
    parser_rel_upd.add_argument('--level', type=int, help="Current level")
    parser_rel_upd.add_argument('--aptitude', type=int, choices=[0, 1, 2, 3, 4],  help="Aptitude (choose between 0-4)")

    # clan
    parser_clan = subparsers.add_parser('clan', help="Clan-wide management")
    clan_subparsers = parser_clan.add_subparsers(dest="clan_cmd")
    # clan status
    clan_subparsers.add_parser('status', help="Show the best folk for every skill")

    args = parser.parse_args(argv)

    if args.cmd == 'rel' and args.rel_cmd == 'add':
        values = (args.skill_id, args.level, args.aptitude)
        if args.interactive and any(value is not None for value in values):
            parser_rel_add.error("--interactive cannot be combined with skill_id, level, or aptitude")
        if not args.interactive and any(value is None for value in values):
            parser_rel_add.error("provide skill_id, level, and aptitude, or use --interactive")

    if args.cmd not in (None, 'init', 'migrate'):
        database.ensure_initialized()

    # Handle CMDs
    if args.cmd == 'init':
        database.init_db()
    elif args.cmd == 'migrate':
        database.migrate_db()
    elif args.cmd == 'skill':
        if args.skill_cmd == 'add':
            database.add_skill(args.name)
        elif args.skill_cmd == 'list':
            all_skills = database.get_all_skills()
            
            if not all_skills:
                print("No skills found. Use 'skill add [name]' to create one.")
            else:
                # Output header
                print(f"\n{'ID':<4} | {'SKILL NAME':<20}")
                print("-" * 25)
                
                for skill in all_skills:
                    print(f"{skill.id:<4} | {skill.name:<20}")
                print("") # Final newline for spacing
        elif args.skill_cmd == 'update':
            database.update_skill(args.id, args.name)
        else:
            parser_skill.print_help()
    elif args.cmd == 'folk':
        if args.folk_cmd == 'add':
            database.add_char(args.name, args.loved, args.hated)
        elif args.folk_cmd == 'list':
            all_folks = database.get_all_chars()

            if not all_folks:
                print("No clanfolk found. Use 'folk add' to create one.")
            else:
                # Output header
                print(f"\n{'ID':<4} | {'NAME':<20} | {'LOVES':<20} | {'HATES':<20}")
                print("-" * 70)
                
                for char, loved_name, hated_name in all_folks:
                    print(f"{char.id:<4} | {char.name:<20} | {loved_name:<20} | {hated_name:<20}")
                print("") # Final newline for spacing
        elif args.folk_cmd == 'update':
            database.update_char(args.id, name=args.name, loved_id=args.loved, hated_id=args.hated)
        elif args.folk_cmd == 'sort':
            char, relations = database.get_folk_priority_data(args.id)
        
            if not relations:
                print(f"{char.name} has no recorded skills. "
                      f"Use 'rel add {args.id} --interactive' to enter levels and aptitudes.")
            else:
                prioritized = sorter.sort_folk_skills(char, relations)
            
                print(f"\n--- Skill Priority for {char.name} ---")
                print(f"{'SKILL':<20} | {'PRIORITY':<5} | {'LEVEL':<5}")
                print("-" * 30)
                for item in prioritized:
                    print(f"{item['name']:<20} | {item['priority']:<5} | {item['level']:<5}")
                print("") # Final newline for spacing
        else:
            parser_folk.print_help()
    elif args.cmd == 'rel':
        if args.rel_cmd == 'add':
            if args.interactive:
                database.get_char(args.char_id)
                all_skills = database.get_all_skills()
                print(f"\n--- Interactive Skill Entry for Folk ID: {args.char_id} ---")
                print("Leave 'Level' blank to skip a skill; no new record is created. "
                      "Unrecorded skills are excluded from rankings. "
                      "Existing records are unchanged. Use Ctrl+C to stop.\n")
                for skill in all_skills:
                    lvl_input = input(f"[{skill.name}] Current Level: ").strip()
                    if not lvl_input:
                        continue
                    try:
                        level = int(lvl_input)
                    except ValueError:
                        raise ValueError("Level must be an integer.") from None
                    while True:
                        apt_input = input(f"[{skill.name}] Aptitude (0-4): ").strip()
                        if apt_input.isdigit() and 0 <= int(apt_input) <= 4:
                            aptitude = int(apt_input)
                            break
                        print("Error: Please enter an aptitude between 0 and 4.", file=sys.stderr)
                    database.add_relation(args.char_id, skill.id, level, aptitude)
                print("\nInteractive session complete!")
            else:
                database.add_relation(args.char_id, args.skill_id, args.level, args.aptitude)
        elif args.rel_cmd == 'update':
            database.update_relation(args.char_id, args.skill_id, current_lvl=args.level, aptitude=args.aptitude)
        else:
            parser_rel.print_help()
    elif args.cmd == 'clan':
        if args.clan_cmd == 'status':
            data = database.get_global_priority_data()
            matrix = sorter.get_global_assignment(data)

            if not matrix:
                print("No eligible candidates in the clan. Candidates need recorded skill "
                      "levels and aptitudes, and hated skills are excluded. "
                      "Use 'folk list' to find a folk ID, then "
                      "'rel add <folk_id> --interactive' to record skills. "
                      "If there are no folks yet, use 'folk add' first.")
                return
            
            print(f"\n{'--- CLAN ASSIGNMENT GUIDE ---':^50}")
            for skill in database.get_all_skills():
                folks = matrix.get(skill.name, [])
                print(f"\n{skill.name.upper()}:")
                if not folks:
                    print("  No eligible candidates: this skill is unrecorded for all folks "
                          "or hated by every folk with a record.")
                # Show top 5 candidates for this skill
                for i, candidate in enumerate(folks[:5]):
                    medal = "🥇" if i == 0 else "  "
                    print(f"  {medal} {candidate['folk']:<12} (Score: {candidate['score']:>5}) | Lvl: {candidate['level']}")
        else:
            parser_clan.print_help()
    else:
        parser.print_help()

def main(argv=None):
    try:
        run(argv)
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except IntegrityError as exc:
        detail = str(exc.orig)
        if "UNIQUE constraint failed: skills.name" in detail:
            message = "A skill with this name already exists. For migration, resolve duplicate names in the original database and retry."
        elif "FOREIGN KEY constraint failed" in detail:
            message = "Referenced folk or skill does not exist. For migration, repair invalid references and retry."
        elif "UNIQUE constraint failed: relations." in detail:
            message = "This folk already has a relation for this skill."
        else:
            message = f"Database constraint violation: {detail}"
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nEntry cancelled. Previously saved entries are retained.", file=sys.stderr)
        return 130
    except EOFError:
        print("\nInput ended. Previously saved entries are retained.", file=sys.stderr)
        return 1
    except Exception:
        logging.exception("Unexpected error; command failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
