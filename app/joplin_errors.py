class JoplinError(Exception):
    pass


class JoplinNotFoundError(JoplinError):
    pass


class JoplinAmbiguousTitleError(JoplinError):
    pass
