from alembic import context

from backend.app.db.models import Base
from backend.app.db.session import get_engine

config = context.config
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=str(get_engine().url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
