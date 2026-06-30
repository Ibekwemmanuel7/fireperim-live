"""Fire-weather enrichment via Open-Meteo (Day 3): wind, RH, temperature."""
from fireperim.weather.open_meteo import WEATHER_COLUMNS, fetch_weather

__all__ = ["fetch_weather", "WEATHER_COLUMNS"]
