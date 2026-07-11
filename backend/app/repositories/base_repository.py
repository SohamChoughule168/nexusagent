from typing import Any, Dict, List, Optional, Type, TypeVar
from sqlalchemy import Session
from sqlalchemy.orm import Query
from contextlib import contextmanager

T = TypeVar('T', bound='Base')

class BaseRepository:
    model: Type[T]

    def __init__(self, db: Session):
        self.db = db
        self.model = self._get_model_type()

    @classmethod
    def _get_model_type(cls) -> Type[T]:
        raise NotImplementedError("Subclasses must implement _get_model_type")

    @contextmanager
    def transaction(self) -> Session:
        try:
            yield self.db
        except Exception as e:
            self.db.rollback()
            raise e

    def get(self, **kwargs) -> Optional[T]:
        """Get a single record by filters"""
        return self._query().filter_by(**kwargs).first()

    def get_or_create(self, **kwargs) -> T:
        """Get or create a record by filters"""
        record = self.get(**kwargs)
        if not record:
            record = self.model(**kwargs)
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        return record

    def get_all(self, **filters) -> List[T]:
        """Get all records with optional filters"""
        query = self._query()
        if filters:
            query = query.filter_by(**filters)
        return query.all()

    def create(self, obj: T) -> T:
        """Create a new record"""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: T) -> T:
        """Update an existing record"""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: T) -> None:
        """Delete a record"""
        self.db.delete(obj)
        self.db.commit()

    def _query(self) -> Query[T]:
        """Get base query with tenant isolation"""
        raise NotImplementedError("Subclasses must implement _query")

class TenantAwareRepository(BaseRepository):
    def __init__(self, db: Session, organization_id: str):
        super().__init__(db)
        self.organization_id = organization_id

    def _query(self) -> Query[T]:
        """Apply tenant isolation filter"""
        return super()._query().filter_by(organization_id=self.organization_id)

# Example repository for Organization
class OrganizationRepository(TenantAwareRepository):
    model = OrganizationModel

    @classmethod
    def _get_model_type(cls) -> Type[OrganizationModel]:
        return OrganizationModel

# Example repository pattern usage
class OrganizationService:
    def __init__(self, db: Session, organization_id: str):
        self.repository = OrganizationRepository(db, organization_id)

    def get_organization(self, organization_id: str) -> Optional[OrganizationModel]:
        return self.repository.get(id=organization_id)