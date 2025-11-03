from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

convention = {
    "ix": "%(table_name)s_%(column_0_label)s",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey", 
    "pk": "%(table_name)s_pkey",
}
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)
