from collections.abc import Mapping, Sequence


def delayed_publication_matches(
    delayed_message: Mapping[int, Sequence[int | float | str]],
    message_id: int,
    sender_id: int | str,
    expected_time: int | float | str,
) -> bool:
    current = delayed_message.get(int(message_id))
    if current is None:
        return False

    current_time, current_sender_id = current
    return int(float(current_time)) == int(float(expected_time)) and int(current_sender_id) == int(sender_id)
