"""Add Row Level Security policies for tenant isolation

Revision ID: 002_rls_policies
Revises: 001_initial_migration
Create Date: 2026-07-12 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_rls_policies'
down_revision = '001_initial_migration'
branch_labels = None
depends_on = None


def upgrade():
    # Enable RLS on tables that require tenant isolation
    # This enforces isolation even if application-level filtering fails

    # Apply RLS to agent-related tables
    op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agents FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversations FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE messages FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tool_executions FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE leads ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leads FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_events FORCE ROW LEVEL SECURITY")

    # Create RLS policies - each requires app.current_org_id to be set
    # This is set in a database session by our application

    op.execute("""
        CREATE POLICY tenant_isolation_agents
        ON agents
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_conversations
        ON conversations
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_messages
        ON messages
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_document_chunks
        ON document_chunks
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_tool_executions
        ON tool_executions
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_leads
        ON leads
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    op.execute("""
        CREATE POLICY tenant_isolation_usage_events
        ON usage_events
        USING (organization_id = current_setting('app.current_org_id')::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org_id')::uuid)
    """)

    # Grant policy usage to application user (adjust as needed).
    # Guard so the migration applies even when the role does not yet exist.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexus_user;
            END IF;
        END
        $$;
        """
    )

    # Create application context function (for RLS to work)
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_org_id(org_id UUID)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_org_id', org_id::text, true);
        END;
        $$ LANGUAGE plpgsql
    """)


def downgrade():
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS tenant_isolation_agents ON agents")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_conversations ON conversations")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_messages ON messages")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_document_chunks ON document_chunks")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_tool_executions ON tool_executions")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_leads ON leads")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_usage_events ON usage_events")

    # Disable RLS
    op.execute("ALTER TABLE agents DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversations DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE messages DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tool_executions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leads DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_events DISABLE ROW LEVEL SECURITY")

    # Drop context function
    op.execute("DROP FUNCTION IF EXISTS set_current_org_id(UUID)")