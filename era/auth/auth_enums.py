from enum import Enum
class AuthRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    FOUNDER = "FOUNDER"
class AuthPermission(str, Enum):
    READ = "READ"
    EXPORT = "EXPORT"
    ADMIN = "ADMIN"
    FOUNDER = "FOUNDER"
