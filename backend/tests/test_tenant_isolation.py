import pytest
from fastapi.testclient import TestClient
from typing import List

from app.main import app
from app.models.user import User
from app.models.organization import Organization
from app.models.all_models import OrganizationMember

from app.services.tenant_context import (
    TenantContext,
    TenantContextResolver,
    RoleManager,
    TenantAccessError,
    MembershipNotFoundError,
    InsufficientPermissionsError,
    tenant_context,
    get_user_tenant_context,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# Test fixtures
def test_user_factory():
    """Create a test user."""
    return User(
        id="550e8400-e29b-41d4-a716-446655440000",
        email="test@example.com",
        is_active=True,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$...",  # Dummy hash
    )


def test_organization_factory() -> Organization:
    """Create a test organization."""
    return Organization(
        id="550e8400-e29b-41d4-a716-446655440001",
        name="Test Organization",
        slug="test-organization",
    )


@pytest.fixture
def test_user():
    return test_user_factory()


@pytest.fixture
def test_organization():
    return test_organization_factory()


def test_tenant_context_resolver_initializes_correctly():
    """Test that TenantContextResolver can be instantiated."""
    from app.core.database import get_sessionmaker as SessionLocal
    db = SessionLocal()()
    resolver = TenantContextResolver(db=db)
    assert resolver is not None
    db.close()


def test_membership_not_found_error():
    """Test MembershipNotFoundError can be raised."""
    with pytest.raises(MembershipNotFoundError):
        raise MembershipNotFoundError("User not a member")


def test_tenant_access_error():
    """Test TenantAccessError can be raised."""
    with pytest.raises(TenantAccessError):
        raise TenantAccessError("Access denied")


def test_insufficient_permissions_error():
    """Test InsufficientPermissionsError can be raised."""
    with pytest.raises(InsufficientPermissionsError):
        raise InsufficientPermissionsError("Not enough permissions")


# --- Integration Tests (require database) ---


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    from app.core.database import get_sessionmaker as SessionLocal
    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def resolver(db_session):
    """Create a TenantContextResolver with a database session."""
    return TenantContextResolver(db=db_session)


@pytest.fixture
def org_owner(db_session):
    """Create an organization owner user and organization."""
    import uuid
    from app.models.organization import Organization
    from app.models.all_models import OrganizationMember

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Create user
    user = User(
        id=str(user_id),
        email=f"owner_{user_id}@example.com",
        is_active=True,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$...",
    )
    db_session.add(user)

    # Create organization
    org = Organization(
        id=str(org_id),
        name=f"Test Org {org_id}",
        slug=f"test-org-{org_id}",
    )
    db_session.add(org)

    # Create membership as owner
    membership = OrganizationMember(
        organization_id=str(org_id),
        user_id=str(user_id),
        role="owner",
    )
    membership.id = uuid.uuid4()
    db_session.add(membership)

    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(org)
    db_session.refresh(membership)

    yield user, org

    # Cleanup
    db_session.delete(membership)
    db_session.delete(org)
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def org_member(db_session, org_owner):
    """Create a member user in the same organization."""
    import uuid
    from app.models.all_models import OrganizationMember

    owner_user, org = org_owner
    member_id = uuid.uuid4()

    # Create member user
    member = User(
        id=str(member_id),
        email=f"member_{member_id}@example.com",
        is_active=True,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$...",
    )
    db_session.add(member)

    # Create membership as member
    membership = OrganizationMember(
        organization_id=str(org.id),
        user_id=str(member_id),
        role="member",
    )
    membership.id = uuid.uuid4()
    db_session.add(membership)

    db_session.commit()
    db_session.refresh(member)
    db_session.refresh(membership)

    yield member, org, membership

    # Cleanup
    db_session.delete(membership)
    db_session.delete(member)
    db_session.commit()


@pytest.fixture
def other_org_user(db_session):
    """Create a user in a different organization."""
    import uuid
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    user = User(
        id=str(user_id),
        email=f"other_{user_id}@example.com",
        is_active=True,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$...",
    )
    db_session.add(user)

    org = Organization(
        id=str(org_id),
        name=f"Other Org {org_id}",
        slug=f"other-org-{org_id}",
    )
    db_session.add(org)

    membership = OrganizationMember(
        organization_id=str(org_id),
        user_id=str(user_id),
        role="owner",
    )
    membership.id = uuid.uuid4()
    db_session.add(membership)

    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(org)
    db_session.refresh(membership)

    yield user, org

    db_session.delete(membership)
    db_session.delete(org)
    db_session.delete(user)
    db_session.commit()


# --- Tenant Context Resolution Tests ---


def test_resolve_context_success(resolver, org_owner):
    """Test successful tenant context resolution for organization owner."""
    user, org = org_owner
    context = resolver.resolve_context(user, org.id)

    assert context.organization_id == org.id
    assert context.user_id == user.id
    assert context.role == "owner"
    assert context.is_owner is True
    assert context.is_admin is True
    assert context.can_manage_members is True
    assert context.can_manage_agents is True
    assert context.can_view_analytics is True
    assert context.can_manage_billing is True


def test_resolve_context_member_role(resolver, org_member):
    """Test tenant context resolution for member role."""
    member, org, membership = org_member
    context = resolver.resolve_context(member, org.id)

    assert context.organization_id == org.id
    assert context.user_id == member.id
    assert context.role == "member"
    assert context.is_owner is False
    assert context.is_admin is False
    assert context.can_manage_members is False
    assert context.can_manage_agents is True
    assert context.can_view_analytics is True
    assert context.can_manage_billing is False


def test_resolve_context_inactive_user_raises(resolver, org_owner):
    """Test that inactive user raises TenantAccessError."""
    user, org = org_owner
    user.is_active = False
    resolver.db.commit()

    with pytest.raises(TenantAccessError, match="User account is inactive"):
        resolver.resolve_context(user, org.id)


def test_resolve_context_non_member_raises(resolver, other_org_user):
    """Test that non-member user raises MembershipNotFoundError."""
    user, org = other_org_user
    # Try to access a different organization
    import uuid
    other_org_id = uuid.uuid4()

    with pytest.raises(MembershipNotFoundError):
        resolver.resolve_context(user, other_org_id)


def test_resolve_context_nonexistent_org_raises(resolver, org_owner):
    """Test that nonexistent organization raises MembershipNotFoundError."""
    user, _ = org_owner
    import uuid
    fake_org_id = uuid.uuid4()

    with pytest.raises(MembershipNotFoundError):
        resolver.resolve_context(user, fake_org_id)


# --- validate_organization_access Tests ---


def test_validate_organization_access_with_required_roles(resolver, org_owner):
    """Test validate_organization_access with required roles."""
    user, org = org_owner
    context = resolver.validate_organization_access(
        user, org.id, required_roles={"owner", "admin"}
    )
    assert context.role == "owner"


def test_validate_organization_access_insufficient_role(resolver, org_member):
    """Test validate_organization_access raises for insufficient role."""
    member, org, _ = org_member
    with pytest.raises(InsufficientPermissionsError):
        resolver.validate_organization_access(
            member, org.id, required_roles={"owner", "admin"}
        )


def test_validate_organization_access_no_required_roles(resolver, org_member):
    """Test validate_organization_access with no required roles (any member)."""
    member, org, _ = org_member
    context = resolver.validate_organization_access(member, org.id, required_roles=None)
    assert context.role == "member"


# --- can_access_organization Tests ---


def test_can_access_organization_true(resolver, org_owner):
    """Test can_access_organization returns True for member."""
    user, org = org_owner
    assert resolver.can_access_organization(user, org.id) is True


def test_can_access_organization_false(resolver, other_org_user):
    """Test can_access_organization returns False for non-member."""
    user, _ = other_org_user
    import uuid
    assert resolver.can_access_organization(user, uuid.uuid4()) is False


# --- get_user_organizations Tests ---


def test_get_user_organizations(resolver, org_owner, org_member):
    """Test get_user_organizations returns all user's organizations."""
    owner_user, owner_org = org_owner
    member_user, member_org, _ = org_member

    owner_orgs = resolver.get_user_organizations(owner_user)
    assert owner_org.id in owner_orgs

    member_orgs = resolver.get_user_organizations(member_user)
    assert member_org.id in member_orgs


# --- TenantContext Permission Properties Tests ---


def test_tenant_context_owner_permissions():
    """Test TenantContext permission properties for owner role."""
    import uuid
    ctx = TenantContext(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
    )
    assert ctx.is_owner is True
    assert ctx.is_admin is True
    assert ctx.can_manage_members is True
    assert ctx.can_manage_agents is True
    assert ctx.can_view_analytics is True
    assert ctx.can_manage_billing is True


def test_tenant_context_admin_permissions():
    """Test TenantContext permission properties for admin role."""
    import uuid
    ctx = TenantContext(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="admin",
    )
    assert ctx.is_owner is False
    assert ctx.is_admin is True
    assert ctx.can_manage_members is True
    assert ctx.can_manage_agents is True
    assert ctx.can_view_analytics is True
    assert ctx.can_manage_billing is False


def test_tenant_context_member_permissions():
    """Test TenantContext permission properties for member role."""
    import uuid
    ctx = TenantContext(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="member",
    )
    assert ctx.is_owner is False
    assert ctx.is_admin is False
    assert ctx.can_manage_members is False
    assert ctx.can_manage_agents is True
    assert ctx.can_view_analytics is True
    assert ctx.can_manage_billing is False


def test_tenant_context_viewer_permissions():
    """Test TenantContext permission properties for viewer role."""
    import uuid
    ctx = TenantContext(
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="viewer",
    )
    assert ctx.is_owner is False
    assert ctx.is_admin is False
    assert ctx.can_manage_members is False
    assert ctx.can_manage_agents is False
    assert ctx.can_view_analytics is True
    assert ctx.can_manage_billing is False


# --- RoleManager Tests ---


def test_role_manager_validate_role():
    """Test RoleManager validate_role method."""
    from app.services.tenant_context import RoleManager
    from app.core.database import get_sessionmaker as SessionLocal

    db = SessionLocal()()
    try:
        manager = RoleManager(db)
        assert manager.validate_role("owner") is True
        assert manager.validate_role("admin") is True
        assert manager.validate_role("member") is True
        assert manager.validate_role("viewer") is True
        assert manager.validate_role("invalid") is False
    finally:
        db.close()


def test_role_manager_can_promote_to():
    """Test RoleManager can_promote_to method."""
    from app.services.tenant_context import RoleManager
    from app.core.database import get_sessionmaker as SessionLocal

    db = SessionLocal()()
    try:
        manager = RoleManager(db)
        assert manager.can_promote_to("owner", "admin") is True
        assert manager.can_promote_to("owner", "member") is True
        assert manager.can_promote_to("owner", "viewer") is True
        assert manager.can_promote_to("admin", "member") is True
        assert manager.can_promote_to("admin", "viewer") is True
        assert manager.can_promote_to("member", "viewer") is True
        assert manager.can_promote_to("owner", "owner") is False
        assert manager.can_promote_to("admin", "admin") is False
        assert manager.can_promote_to("member", "member") is False
        assert manager.can_promote_to("viewer", "viewer") is False
        assert manager.can_promote_to("admin", "owner") is False
        assert manager.can_promote_to("member", "admin") is False
    finally:
        db.close()


def test_role_manager_can_demote_from():
    """Test RoleManager can_demote_from method."""
    from app.services.tenant_context import RoleManager
    from app.core.database import get_sessionmaker as SessionLocal

    db = SessionLocal()()
    try:
        manager = RoleManager(db)
        assert manager.can_demote_from("owner", "admin") is True
        assert manager.can_demote_from("admin", "member") is True
        assert manager.can_demote_from("member", "viewer") is True
        assert manager.can_demote_from("owner", "owner") is False
    finally:
        db.close()


# --- Tenant Context Context Manager Tests ---


def test_tenant_context_manager():
    """Test tenant_context context manager yields context."""
    import uuid
    from app.core.database import get_sessionmaker as SessionLocal
    from app.services.tenant_context import tenant_context

    db = SessionLocal()()
    try:
        org_id = uuid.uuid4()
        with tenant_context(db, org_id) as ctx:
            assert ctx.organization_id == org_id
            assert ctx.role == "member"
    finally:
        db.close()


# --- Integration Tests with Real Database ---


@pytest.mark.integration
def test_full_tenant_isolation_workflow(db_session, resolver):
    """Integration test: full tenant isolation workflow."""
    import uuid
    from app.models.user import User
    from app.models.organization import Organization
    from app.models.all_models import OrganizationMember

    # Create two organizations
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()

    org1 = Organization(id=str(org1_id), name="Org 1", slug=f"org1-{org1_id}")
    org2 = Organization(id=str(org2_id), name="Org 2", slug=f"org2-{org2_id}")
    db_session.add_all([org1, org2])

    # Create users (unique emails so repeated runs don't collide)
    user1 = User(id=str(uuid.uuid4()), email=f"user1-{org1_id}@example.com", is_active=True, password_hash="hash")
    user2 = User(id=str(uuid.uuid4()), email=f"user2-{org2_id}@example.com", is_active=True, password_hash="hash")
    db_session.add_all([user1, user2])

    # User1 is member of org1 (owner)
    mem1 = OrganizationMember(organization_id=str(org1_id), user_id=user1.id, role="owner")
    mem1.id = uuid.uuid4()
    # User2 is member of org2 (owner)
    mem2 = OrganizationMember(organization_id=str(org2_id), user_id=user2.id, role="owner")
    mem2.id = uuid.uuid4()
    # User1 is also member of org2 (member)
    mem3 = OrganizationMember(organization_id=str(org2_id), user_id=user1.id, role="member")
    mem3.id = uuid.uuid4()
    db_session.add_all([mem1, mem2, mem3])

    db_session.commit()

    # User1 can access org1
    assert resolver.can_access_organization(user1, org1_id) is True
    ctx1 = resolver.resolve_context(user1, org1_id)
    assert ctx1.role == "owner"

    # User1 can access org2 as member
    assert resolver.can_access_organization(user1, org2_id) is True
    ctx2 = resolver.resolve_context(user1, org2_id)
    assert ctx2.role == "member"

    # User2 cannot access org1
    assert resolver.can_access_organization(user2, org1_id) is False
    with pytest.raises(MembershipNotFoundError):
        resolver.resolve_context(user2, org1_id)

    # User2 can access org2
    assert resolver.can_access_organization(user2, org2_id) is True
    ctx3 = resolver.resolve_context(user2, org2_id)
    assert ctx3.role == "owner"

    # Cleanup
    db_session.delete(mem3)
    db_session.delete(mem2)
    db_session.delete(mem1)
    db_session.delete(user2)
    db_session.delete(user1)
    db_session.delete(org2)
    db_session.delete(org1)
    db_session.commit()


# Test that test file runs without import errors
def test_imports_work():
    """Sanity check that all imports work."""
    assert TenantContextResolver is not None
    assert TenantAccessError is not None
    assert MembershipNotFoundError is not None
    assert InsufficientPermissionsError is not None
    assert TenantContext is not None
    assert RoleManager is not None
    assert RoleManager is not None
    assert tenant_context is not None
    assert get_user_tenant_context is not None