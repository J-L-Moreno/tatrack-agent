from tools import TASK_TOOLS, get_current_datetime


def get_tools() -> list:
    """Tools exposed to the model. load_skill is added by SkillMiddleware."""
    return [get_current_datetime, *TASK_TOOLS]
