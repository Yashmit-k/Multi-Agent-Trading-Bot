from core_api.app import create_app
from core_api.settings import Settings

app = create_app(Settings.from_env(), seed=True)
