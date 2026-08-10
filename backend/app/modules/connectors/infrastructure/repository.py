from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.connectors.infrastructure.models import Connector, RawEvent


class ConnectorRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, connector_id: UUID) -> Connector | None:
        """Deliberately NOT org-scoped — the ingest endpoint is called by
        an external system with only the connector's own secret, not a
        user JWT carrying an org_id. Org scoping for ingest happens via
        the connector row itself (it already knows its org_id); every
        other method in this repository IS org-scoped since those are
        called from authenticated admin requests."""
        return self.db.get(Connector, connector_id)

    def get_by_id_for_org(self, org_id: UUID, connector_id: UUID) -> Connector | None:
        stmt = select(Connector).where(Connector.id == connector_id, Connector.org_id == org_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_org(self, org_id: UUID) -> list[Connector]:
        stmt = select(Connector).where(Connector.org_id == org_id).order_by(Connector.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def create(self, connector: Connector) -> Connector:
        self.db.add(connector)
        self.db.flush()
        return connector

    def save(self, connector: Connector) -> Connector:
        self.db.flush()
        return connector

    def delete(self, connector: Connector) -> None:
        self.db.delete(connector)
        self.db.flush()

    def add_raw_event(self, event: RawEvent) -> RawEvent:
        self.db.add(event)
        self.db.flush()
        return event
