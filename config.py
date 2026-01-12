class Settings:
    api_token_bot = "АПИ токен телеграмма"
    general_admin: int = "Главный админ"
    moderators: set = set()
    hello_msg: str = "hello"
    ban_msg: str = "ban"


settings = Settings()