from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core_database.config import settings


class DataBaseHelper:
    def __init__(self, url: str, echo: bool = False):
        self.engine = create_engine(
            url=url,
            echo=echo,
        )

        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )


db_helper = DataBaseHelper(
    url=settings.database_url,
    echo=settings.db_echo,
)
