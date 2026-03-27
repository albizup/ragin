from ragin import ServerlessApp

# Import your models so @resource decorators are registered
from models import *  # noqa: F401, F403


app = ServerlessApp()
