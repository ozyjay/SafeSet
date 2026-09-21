from uuid import UUID, uuid4


def new_id() -> str:
    return str(uuid4())


def valid_id(value: str) -> bool:
    try:
        parsed = UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except (ValueError, AttributeError, TypeError):
        return False
