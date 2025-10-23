from pydantic_settings import BaseSettings
from pydantic import Extra
from typing import List
import os

class Settings(BaseSettings):
    GOOGLE_API_KEY : str
    GROQ_API_KEY : str
    COHERE_API_KEY : str

    POSTGRES_USER : str
    POSTGRES_DB : str
    POSTGRES_PASSWORD : str
    DATABASE_URL : str

    class Config:
        # Get the absolute path to the project root
        project_root = os.path.dirname(os.path.abspath(__file__))
        env_file = os.path.join(project_root, ".env")
        env_prefix = ""  # Add this line to remove any prefix for environment variables

def get_settings() -> Settings:
    return Settings()