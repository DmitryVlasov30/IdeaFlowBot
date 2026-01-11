from sqlalchemy import insert, select, and_, delete, update

from src.core_database.models.base import Base
from src.core_database.models.banned_user import BannedUser
from src.core_database.models.db_helper import db_helper


def create_table():
    Base.metadata.create_all(db_helper.engine)


def drop_table():
    Base.metadata.drop_all(db_helper.engine)


class CrudBannedUser:
    @staticmethod
    def get_banned_users():
        with db_helper.engine.connect() as conn:
            result = conn.execute(select(BannedUser)).fetchall()
            return result

    @staticmethod
    def add_banned_user(user: dict):
        with db_helper.engine.connect() as conn:
            stmt = (
                insert(BannedUser).values(user)
            )
            conn.execute(stmt)
            conn.commit()

    @staticmethod
    def delete_banned_user(user: dict):
        with db_helper.engine.connect() as conn:
            stmt = (
                delete(BannedUser)
                .filter(and_(
                    BannedUser.id_user == user["id_user"],
                    BannedUser.id_channel == user["id_channel"]
                ))
            )
            conn.execute(stmt)
            conn.commit()
