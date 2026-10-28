def validate_name(name, limit, label):
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} name cannot be blank.")
    name = name.strip()
    if len(name) > limit:
        raise ValueError(f"{label} name is too long (max {limit} characters).")
    return name


class Character:
    def __init__(self, name, loved_id, hated_id, id=None, created_at=None):
        self.id = id
        self.name = validate_name(name, 50, "Folk")
        self.loved_id = loved_id
        self.hated_id = hated_id
        self.created_at = created_at
        
        # Block adding one skill as liked and hated, as those are mutually exclusive
        if self.loved_id == self.hated_id:
            raise ValueError(f"Liked and hated skill cannot be the same")
    
    def __repr__(self):
        return f'Character("{self.name}","{self.loved_id}","{self.hated_id}")'

class Skill:
    def __init__(self, name, id=None, created_at=None):
        self.id = id
        self.name = validate_name(name, 20, "Skill")
        self.created_at = created_at

    def __repr__(self):
        return f'Skill(name={self.name})'

class SkillRelation:
    # Aptitude - Max lvl map
    APTITUDE_MAP = {0: 5, 1: 10, 2: 12, 3: 14, 4: 15}

    def __init__(self, character_id, skill_id, current_lvl, aptitude, max_lvl=None, created_at=None):
        if type(aptitude) is not int or aptitude not in self.APTITUDE_MAP:
            raise ValueError("Aptitude must be an integer between 0 and 4.")
        expected_max = self.APTITUDE_MAP[aptitude]
        if max_lvl is not None and max_lvl != expected_max:
            raise ValueError("Maximum level must match aptitude.")
        if type(current_lvl) is not int or not 0 <= current_lvl <= expected_max:
            raise ValueError(f"Level must be an integer between 0 and {expected_max} for aptitude {aptitude}.")
        self.character_id = character_id
        self.skill_id = skill_id
        self.current_lvl = current_lvl
        self.aptitude = aptitude
        self.created_at = created_at

        self.max_lvl = expected_max

    def __repr__(self):
        return f'SkillRelation(Char:"{self.character_id}", Skill:"{self.skill_id}", Lvl:"{self.current_lvl}"/"{self.max_lvl}")'