import sketchShared
from sketchShared import debug, info, warn, error, critical
from sqlalchemy import TypeDecorator, String, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, AsyncSession, create_async_engine
import datetime
import sketchAuth

# https://docs.sqlalchemy.org/en/20/core/custom_types.html#augmenting-existing-types
# a customised String type that automatically truncates its value on insert.
class TString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        return value[:self.impl.length]

    def copy(self, **kw):
        return TString(self.impl.length)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class SketchUser(Base):
    __tablename__ = 'users'

    # https://docs.sqlalchemy.org/en/20/orm/quickstart.html#declare-models
    # https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Column.__init__
    # - primarykey: If True, marks this column as a primary key column. Multiple columns can have this flag set to specify composite primary keys. As an alternative, the primary key of a Table can be specified via an explicit PrimaryKeyConstraint object.
    # - autoincrement: The default value is the String "auto", which indicates that a single-column (i.e. non-composite) primary key that is of an INTEGER type with no other client-side or server-side default constructs indicated should receive auto increment semantics automatically.
    # - nullable: When set to False, will cause the “NOT NULL” phrase to be added when generating DDL for the column. Defaults to True unless Column.primary_key is also True or the column specifies a Identity, in which case it defaults to False.
    # - default: A scalar, Python callable, or ColumnElement expression representing the default value for this column, which will be invoked upon insert if this column is otherwise not specified in the VALUES clause of the insert. This is a shortcut to using ColumnDefault as a positional argument; A plain default value on a column. This could correspond to a constant, a callable function, or a SQL clause. ColumnDefault is generated automatically whenever the default, onupdate arguments of Column are used. A ColumnDefault can be passed positionally as well.
    sketchId: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    userName: Mapped[str] = mapped_column(TString(50), nullable=True, default='')
    
class SketchConnection(Base):
    __tablename__ = 'connections'

    sketchId: Mapped[int] = mapped_column(ForeignKey('users.sketchId', onupdate='CASCADE', ondelete='CASCADE'), autoincrement=False, primary_key=True)
    serviceName: Mapped[str] = mapped_column(TString(50), primary_key=True)
    serviceId: Mapped[int] = mapped_column(TString(255), primary_key=True)

class SketchYoutube(Base):
    __tablename__ = 'youtube'

    youtubeId: Mapped[str] = mapped_column(TString(255), primary_key=True)
    channelId: Mapped[str] = mapped_column(TString(50), primary_key=True)
    refreshToken: Mapped[str] = mapped_column(TString(5000))
    accessToken: Mapped[str] = mapped_column(TString(5000))
    accessExpires: Mapped[datetime.datetime]
    scheduling: Mapped[bool] = mapped_column(nullable=False, default=False)
    monitoring: Mapped[bool] = mapped_column(nullable=False, default=False)

class SketchYoutubeVideo(Base):
    __tablename__ = 'youtubeVideos'
    
    videoId: Mapped[str] = mapped_column(TString(50), primary_key=True)
    channelId: Mapped[str] = mapped_column(TString(50), nullable=False)
    title: Mapped[str] = mapped_column(TString(100))
    privacyStatus: Mapped[str] = mapped_column(TString(50))
    thumbnailUrl: Mapped[str] = mapped_column(TString(2038))
    publishAt: Mapped[datetime.datetime]

async def createDatabase():
    engine = create_async_engine("mariadb+asyncmy://root:sketch@localhost:3306/sketch", echo=True)


async def connectDatabase():
    global db
    info('Connecting database...')