"""Register the components available to the dashboard and settings page."""
from .codex import COMPONENT as codex
from .github import COMPONENT as github
from .pet_panda import COMPONENT as panda
from .pet_corgi import COMPONENT as corgi

COMPONENTS = {component['id']: component for component in (codex, github, panda, corgi)}
