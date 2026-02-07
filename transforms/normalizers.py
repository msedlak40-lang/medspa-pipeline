def normalize_card_type(value: str) -> str:
    """
    Normalize EMR and Gravity card types to:
      'vs' (Visa), 'mc' (MasterCard), 'dc' (Discover), 'ax' (Amex)
    """
    if value is None:
        return ""
    v = str(value).strip().lower()
    mapping = {
        "visa": "vs", "vs": "vs", "v": "vs",
        "mastercard": "mc", "master card": "mc", "mc": "mc",
        "discover": "dc", "disc": "dc", "dc": "dc",
        "amex": "ax", "american express": "ax", "ax": "ax",
    }
    return mapping.get(v, v)
