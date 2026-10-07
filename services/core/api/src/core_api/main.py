from core_api.app import create_app
from core_api.settings import Settings
from core_market_data.kite_client import kite_client_from_env

app = create_app(Settings.from_env(), seed=True, kite_client=kite_client_from_env())
