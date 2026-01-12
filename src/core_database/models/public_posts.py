from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base


class PublicPosts(Base):
    __tablename__ = 'public_posts'

    posts_title: Mapped[str]
    channel_id: Mapped[int]
