import sketchShared
from sketchShared import debug, info, warn, error, critical
from sqlalchemy import TypeDecorator, String, Boolean, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.sql import expression
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import datetime, logging
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

# https://docs.sqlalchemy.org/en/20/orm/quickstart.html#declare-models
# https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Column.__init__
class SketchUser(Base):
    __tablename__ = 'users'

    # - primarykey: If True, marks this column as a primary key column. Multiple columns can have this flag set to specify composite primary keys. As an alternative, the primary key of a Table can be specified via an explicit PrimaryKeyConstraint object.
    # - autoincrement: The default value is the String "auto", which indicates that a single-column (i.e. non-composite) primary key that is of an INTEGER type with no other client-side or server-side default constructs indicated should receive auto increment semantics automatically.
    sketchId: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    # - nullable: When set to False, will cause the “NOT NULL” phrase to be added when generating DDL for the column. Uses the presence of "Optional[]" type hint to determine if its null or not, if there's no "mapped_column" and no nullable=False then it will default to not allowing the column to be null (adds NOT NULL)
    # - default: A scalar, Python callable, or ColumnElement expression representing the default value for this column, which will be invoked upon insert if this column is otherwise not specified in the VALUES clause of the insert. This is a shortcut to using ColumnDefault as a positional argument; A plain default value on a column. This could correspond to a constant, a callable function, or a SQL clause. ColumnDefault is generated automatically whenever the default, onupdate arguments of Column are used. A ColumnDefault can be passed positionally as well.
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
    refreshToken: Mapped[str] = mapped_column(TString(5000), nullable=True)
    accessToken: Mapped[str] = mapped_column(TString(5000), nullable=True)
    accessExpires: Mapped[datetime.datetime] = mapped_column(nullable=True)
    scheduling: Mapped[bool] = mapped_column(nullable=False, server_default=expression.false(), default=False)
    monitoring: Mapped[bool] = mapped_column(nullable=False, server_default=expression.false(), default=False)

class SketchYoutubeVideo(Base):
    __tablename__ = 'youtubeVideos'
    
    videoId: Mapped[str] = mapped_column(TString(50), primary_key=True)
    channelId: Mapped[str] = mapped_column(TString(50), nullable=False)
    title: Mapped[str] = mapped_column(TString(100), nullable=True)
    privacyStatus: Mapped[str] = mapped_column(TString(50), nullable=True)
    thumbnailUrl: Mapped[str] = mapped_column(TString(2083), nullable=True)
    publishAt: Mapped[datetime.datetime] = mapped_column(nullable=True)

async def createDatabase():
    warn('Creating/replacing main Sketch database...')

    async with dbEngine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

# https://docs.sqlalchemy.org/en/20/tutorial/index.html
async def connectDatabase():
    global dbEngine, db
    info('Connecting to database...')

    logging.getLogger('sqlalchemy').setLevel(logging.INFO)

    # https://docs.sqlalchemy.org/en/20/dialects/mysql.html#module-sqlalchemy.dialects.mysql.asyncmy
    dbEngine = create_async_engine('mariadb+asyncmy://sketch:' + sketchAuth.dbPassword + '@localhost:3306/sketch', pool_pre_ping=True, pool_recycle=3600)
    
    # db: an async_sessionmaker factory for new AsyncSession objects.
    # expire_on_commit - don't expire objects after transaction commit
    db = async_sessionmaker(dbEngine, expire_on_commit=False)

    sketchShared.dbengine = dbEngine
    sketchShared.db = db