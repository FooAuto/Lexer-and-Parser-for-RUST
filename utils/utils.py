
def serialize_token(token):
    return {
        key: (value.name if hasattr(value, 'name') else value)
        for key, value in token.items()
    }