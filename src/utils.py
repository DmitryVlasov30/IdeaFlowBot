from core_database.database import CrudBannedUser
from src.core_database.models.db_helper import db_helper


class Utils:
    @staticmethod
    def check_banned_user(id_user: int, id_channel: int) -> bool:
        db_session = CrudBannedUser()
        all_info = db_session.get_banned_users(id_user=id_user, id_channel=id_channel)
        return bool(all_info)
