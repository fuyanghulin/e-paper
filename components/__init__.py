"""Register the components available to the dashboard and settings page."""
from .codex import COMPONENT as codex
from .github import COMPONENT as github
from .pet_panda import COMPONENT as panda
from .pet_corgi import COMPONENT as corgi
from .gta6 import COMPONENT as gta6
from .oa_tasks import COMPONENTS as oa_tasks

COMPONENTS = {component['id']: component for component in (codex, github, panda, corgi, gta6, *oa_tasks)}
