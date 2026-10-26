from sqlalchemy import Select, select

from app.auth.authz import visible_to
from app.auth.principal import Principal
from app.db.models import Job, Perm, Source


def visible_jobs_stmt(p: Principal) -> Select[Job]:
    """Jobs whose source the principal may `use` (admins see all)."""
    stmt: Select[Job] = select(Job).join(Source, Source.id == Job.source_id)
    return visible_to(stmt, Source, p, Perm.use)
