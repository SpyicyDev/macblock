class MacblockError(Exception):
    pass


class UnsupportedPlatformError(MacblockError):
    pass


class PrivilegeError(MacblockError):
    pass
