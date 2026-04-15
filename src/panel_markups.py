from __future__ import annotations

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_main_panel(is_general_admin: bool) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Обновить входящие", callback_data="panel:import"),
        InlineKeyboardButton("Поступившие сообщения", callback_data="panel:submissions"),
    )
    markup.add(
        InlineKeyboardButton("Все сообщения", callback_data="panel:all_submissions"),
        InlineKeyboardButton("Черновики на review", callback_data="panel:content"),
    )
    markup.add(
        InlineKeyboardButton("Пасты", callback_data="panel:pastes"),
        InlineKeyboardButton("Каналы и слоты", callback_data="panel:channels"),
    )
    markup.add(
        InlineKeyboardButton("Запустить scheduler", callback_data="panel:scheduler"),
        InlineKeyboardButton("Запустить publisher", callback_data="panel:publisher"),
    )
    if is_general_admin:
        markup.add(
            InlineKeyboardButton("Сабботы", callback_data="panel:subbots"),
            InlineKeyboardButton("Модераторы", callback_data="panel:admins"),
        )
    return markup


def build_submission_actions(
    submission_id: int,
    has_next: bool,
    is_anonymous: bool,
    allow_moderation: bool = True,
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    if allow_moderation:
        markup.add(
            InlineKeyboardButton("Approve", callback_data=f"submission:approve:{submission_id}"),
            InlineKeyboardButton("Publish now", callback_data=f"submission:publish:{submission_id}"),
        )
        markup.add(
            InlineKeyboardButton("Save as paste", callback_data=f"submission:paste:{submission_id}"),
            InlineKeyboardButton("Hold", callback_data=f"submission:hold:{submission_id}"),
        )
        markup.add(
            InlineKeyboardButton("Анон" if is_anonymous else "Не анон", callback_data=f"submission:toggle_anon:{submission_id}"),
            InlineKeyboardButton("Реклама", callback_data=f"submission:advertise:{submission_id}"),
        )
        markup.add(
            InlineKeyboardButton("Ответить", callback_data=f"submission:reply:{submission_id}"),
            InlineKeyboardButton("Reject", callback_data=f"submission:reject:{submission_id}"),
        )
        markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    else:
        markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    if has_next:
        markup.add(InlineKeyboardButton("Следующее сообщение", callback_data=f"submission:next:{submission_id}"))
    return markup


def build_submission_history_actions(
    submission_id: int,
    has_next: bool,
    is_anonymous: bool,
    allow_moderation: bool = True,
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    if allow_moderation:
        markup.add(
            InlineKeyboardButton("Approve", callback_data=f"submission:approve:{submission_id}"),
            InlineKeyboardButton("Publish now", callback_data=f"submission:publish:{submission_id}"),
        )
        markup.add(
            InlineKeyboardButton("Save as paste", callback_data=f"submission:paste:{submission_id}"),
            InlineKeyboardButton("Hold", callback_data=f"submission:hold:{submission_id}"),
        )
        markup.add(
            InlineKeyboardButton("Анон" if is_anonymous else "Не анон", callback_data=f"submission:toggle_anon:{submission_id}"),
            InlineKeyboardButton("Реклама", callback_data=f"submission:advertise:{submission_id}"),
        )
        markup.add(
            InlineKeyboardButton("Ответить", callback_data=f"submission:reply:{submission_id}"),
            InlineKeyboardButton("Reject", callback_data=f"submission:reject:{submission_id}"),
        )
        markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    else:
        markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    if has_next:
        markup.add(InlineKeyboardButton("Следующее сообщение", callback_data=f"submission_all:next:{submission_id}"))
    return markup


def build_content_actions(content_item_id: int, has_next: bool) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Approve", callback_data=f"content:approve:{content_item_id}"),
        InlineKeyboardButton("Publish now", callback_data=f"content:publish:{content_item_id}"),
    )
    markup.add(
        InlineKeyboardButton("Hold", callback_data=f"content:hold:{content_item_id}"),
        InlineKeyboardButton("Reject", callback_data=f"content:reject:{content_item_id}"),
    )
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    if has_next:
        markup.add(InlineKeyboardButton("Следующий черновик", callback_data=f"content:next:{content_item_id}"))
    return markup


def build_channels_actions(channel_buttons: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for channel_id, title in channel_buttons:
        markup.add(InlineKeyboardButton(title, callback_data=f"channel:view:{channel_id}"))
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    return markup


def build_channel_slots_actions(channel_id: int, slot_buttons: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Добавить слот", callback_data=f"channel:add_slot:{channel_id}"),
        InlineKeyboardButton("Удалить слоты", callback_data=f"channel:delete_slots:{channel_id}"),
        InlineKeyboardButton("Создать стандартные слоты", callback_data=f"channel:seed:{channel_id}"),
    )
    markup.add(InlineKeyboardButton("Назад к каналам", callback_data="panel:channels"))
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    return markup


def build_paste_actions(paste_id: int, has_next: bool) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Добавить пасту", callback_data="paste:add"),
        InlineKeyboardButton("Удалить пасту", callback_data=f"paste:delete:{paste_id}"),
    )
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    if has_next:
        markup.add(InlineKeyboardButton("Следующая паста", callback_data=f"paste:next:{paste_id}"))
    return markup


def build_empty_paste_actions() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("Добавить пасту", callback_data="paste:add"))
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    return markup


def build_admin_menu(admin_buttons: list[int]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("Добавить модератора", callback_data="admin:add"))
    for admin_id in admin_buttons:
        markup.add(InlineKeyboardButton(f"Удалить {admin_id}", callback_data=f"admin:remove:{admin_id}"))
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    return markup


def build_subbot_menu(subbot_buttons: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("Добавить саббота", callback_data="subbot:add"))
    for username, channel_id in subbot_buttons:
        markup.add(InlineKeyboardButton(f"Удалить @{username}", callback_data=f"subbot:remove:{username}:{channel_id}"))
    markup.add(InlineKeyboardButton("Назад в панель", callback_data="panel:main"))
    return markup
