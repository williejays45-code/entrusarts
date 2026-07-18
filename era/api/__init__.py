__all__ = ["app", "create_app"]


def __getattr__(name):
    if name in __all__:
        from era.api import service
        return getattr(service, name)
    raise AttributeError(name)
