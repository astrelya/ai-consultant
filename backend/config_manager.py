import os
from dotenv import load_dotenv, set_key
from sqlalchemy.orm import Session
from backend.database import SessionLocal, ConfigModel

# Load initial .env file
load_dotenv()

# The path to the .env file in the workspace root
ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

class ConfigManager:
    @staticmethod
    def get(key: str, default: str = None) -> str:
        """
        Get configuration value. Checks database first, then environment variables, 
        and falls back to the default value.
        """
        db: Session = SessionLocal()
        try:
            db_config = db.query(ConfigModel).filter(ConfigModel.key == key).first()
            if db_config is not None:
                return db_config.value
        except Exception as e:
            print(f"[ConfigManager] Error reading config from db: {e}")
        finally:
            db.close()
            
        # Fallback to environment variable or default
        return os.environ.get(key, default)

    @staticmethod
    def set(key: str, value: str):
        """
        Sets a configuration value in both the database, the active environment,
        and persists it to the .env file.
        """
        # 1. Update database
        db: Session = SessionLocal()
        try:
            db_config = db.query(ConfigModel).filter(ConfigModel.key == key).first()
            if db_config:
                db_config.value = value
            else:
                db_config = ConfigModel(key=key, value=value)
                db.add(db_config)
            db.commit()
        except Exception as e:
            print(f"[ConfigManager] Error writing config to db: {e}")
            db.rollback()
        finally:
            db.close()

        # 2. Update active environment
        os.environ[key] = value

        # 3. Persist to .env file
        try:
            if os.path.exists(ENV_FILE_PATH):
                set_key(ENV_FILE_PATH, key, value)
            else:
                with open(ENV_FILE_PATH, "w") as f:
                    f.write(f"{key}={value}\n")
        except Exception as e:
            print(f"[ConfigManager] Error writing to .env file: {e}")

    @staticmethod
    def get_all() -> dict:
        """
        Retrieves all database configuration values along with key environment configurations.
        """
        configs = {}
        # Fetch from DB
        db: Session = SessionLocal()
        try:
            db_configs = db.query(ConfigModel).all()
            for cfg in db_configs:
                configs[cfg.key] = cfg.value
        except Exception as e:
            print(f"[ConfigManager] Error loading db configs: {e}")
        finally:
            db.close()

        # List of critical environment variables to include
        keys_to_include = [
            "JIRA_URL", "JIRA_USER", "JIRA_API_TOKEN", "GITHUB_TOKEN", 
            "GITHUB_OWNER", "GEMINI_API_KEY", "CONTEXT7_API_KEY", 
            "TICKET_SYSTEM", "TICKET_MODEL", "CODING_MODEL", "AGENT_MODE",
            "DATABASE_URL"
        ]
        
        for k in keys_to_include:
            if k not in configs:
                configs[k] = os.environ.get(k, "")
                
        return configs
