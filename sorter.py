def calculate_priority(relation: int, loved_id: int, hated_id: int) -> int:
    """
    Returns a score for a skill. Higher = higher priority.
    Rules:
    - Higher aptitude = higher priority (unless aptitude 0 = penalty)
    - Higher current level = higher priority (unless current level 0 = penalty)
    - Bonus for liked skills
    - Penalty for hated skills
    """
    
    # Base score starts at 0
    score = 0
    
    # Aptitude bonus/penalty (0-4)
    if relation.aptitude == 0:
        # Penalty for aptitude 0
        score -= 15
    else:
        # Bonus for higher aptitude (1-4)
        score += relation.aptitude * 5
    
    # Current level bonus/penalty (0-5)
    if relation.current_lvl == 0:
        # Penalty for level 0 (takes time to level up)
        score -= 10
    else:
        # Bonus for higher current levels
        score += relation.current_lvl * 3
    
    # Passion modifiers
    if relation.skill_id == loved_id:
        score += 30  # Bonus for things they love
    elif relation.skill_id == hated_id:
        score -= 100  # Penalty for things they hate
    
    # Additional bonus for skills that are close to max level (high potential)
    # This gives a small boost to skills that are almost max level
    if relation.current_lvl >= relation.max_lvl - 1:
        score += 5
    
    return score

def sort_folk_skills(character: str, relations_with_names: str) -> list:
    """
    Takes a character and a list of their skill relations.
    Returns a list sorted by priority score.
    """
    sorted_list = []
    
    for rel, skill_name in relations_with_names:
        priority = calculate_priority(rel, character.loved_id, character.hated_id)
        sorted_list.append({
            "name": skill_name,
            "priority": priority,
            "level": f"{rel.current_lvl}/{rel.max_lvl}",
            "aptitude": rel.aptitude
        })
        
    # Sort by priority score (descending)
    return sorted(sorted_list, key=lambda x: x['priority'], reverse=True)

def get_global_assignment(all_data):
    # Dictionary to hold: { "Farming": [list of folks + scores], "Mining": [...] }
    matrix = {}

    for char, rel, skill_name in all_data:
        score = calculate_priority(rel, char.loved_id, char.hated_id)
        
        if rel.skill_id == char.hated_id:
            continue
            
        if skill_name not in matrix:
            matrix[skill_name] = []
            
        matrix[skill_name].append({
            "folk": char.name,
            "score": score,
            "level": f"{rel.current_lvl}/{rel.max_lvl}"
        })

    # Sort each skill group so the best folk is at the top
    for skill in matrix:
        matrix[skill] = sorted(matrix[skill], key=lambda x: x['score'], reverse=True)
        
    return matrix