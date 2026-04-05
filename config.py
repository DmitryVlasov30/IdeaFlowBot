class Settings:
    api_token_bot = "АПИ токен телеграмма"
    general_admin: int = 0
    moderators: set = set()
    hello_msg: str = "Здравствуйте!\n\nНапишите Ваш вопрос, и мы ответим Вам в ближайшее время"
    ban_msg: str = "К сожалению администратор предложки дал вам бан("
    send_post_msg: str = ("Спасибо за пост, мы опубликуем его в скором времени\n\n"
                          "Просьба не спамить, все посты публикуются в порядке очереди")
    logging_path: str = r"Путь для файла с логированием"
    const_time_sleep: float = "интервал проверки постов с отложки"
    proxy_user: str = "логин прокси"
    proxy_password: str = "пароль прокси"
    proxy_host_port: str = "сервер прокси:порт прокси"
    shift_time_seconds: int = "время, на которое будет происходить сдвиг при рекламе"
    sup_bot_limit: int = "лимит открытых сессий для ботов"
    advertiser: list = "список админов, которые занимаются рекламой"
    proxies: dict = {
        'http': f'http://{proxy_user}:{proxy_password}@{proxy_host_port}',
        'https': f'http://{proxy_user}:{proxy_password}@{proxy_host_port}'
    }


settings = Settings()
