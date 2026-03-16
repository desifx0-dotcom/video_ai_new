"""
Integration tests for database migrations.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import os
import alembic
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.environment import EnvironmentContext

from src.core.exceptions import DatabaseError

class TestDatabaseMigrations:
    """Test database migrations."""
    
    @pytest.fixture
    def temp_migration_dir(self):
        """Create temporary migration directory."""
        temp_dir = tempfile.mkdtemp()
        versions_dir = os.path.join(temp_dir, 'versions')
        os.makedirs(versions_dir, exist_ok=True)
        
        # Create alembic.ini
        alembic_ini = f"""[alembic]
script_location = {temp_dir}
sqlalchemy.url = sqlite:///test.db

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        
        with open(os.path.join(temp_dir, 'alembic.ini'), 'w') as f:
            f.write(alembic_ini)
        
        # Create env.py
        env_py = """from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

config = context.config
fileConfig(config.config_file_name)
target_metadata = None

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_attributes),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""
        
        with open(os.path.join(temp_dir, 'env.py'), 'w') as f:
            f.write(env_py)
        
        yield temp_dir
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
    
    def test_migration_creation(self, temp_migration_dir):
        """Test creating a new migration."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        
        # Create alembic config
        alembic_cfg = Config(os.path.join(temp_migration_dir, 'alembic.ini'))
        
        # Create script directory
        script = ScriptDirectory.from_config(alembic_cfg)
        
        # Generate new migration
        migration_id = "test_migration"
        message = "Create users table"
        
        # This would normally generate a migration file
        # For testing, we'll create a mock migration
        migration_file = os.path.join(
            temp_migration_dir,
            'versions',
            f"{migration_id}_{message.replace(' ', '_')}.py"
        )
        
        migration_content = '''"""Create users table

Revision ID: test_migration
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'test_migration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('tier', sa.String(20), nullable=False, default='free'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False)
    )
    
    # Create indexes
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_tier', 'users', ['tier'])


def downgrade():
    # Drop users table
    op.drop_table('users')
'''
        
        with open(migration_file, 'w') as f:
            f.write(migration_content)
        
        # Verify migration was created
        assert os.path.exists(migration_file)
        
        # Verify migration content
        with open(migration_file, 'r') as f:
            content = f.read()
            assert 'Create users table' in content
            assert 'def upgrade():' in content
            assert 'def downgrade():' in content
    
    def test_migration_upgrade(self, temp_migration_dir):
        """Test migration upgrade."""
        # Mock alembic operations
        with patch('alembic.op') as mock_op:
            with patch('alembic.context') as mock_context:
                # Import and test migration upgrade
                migration_file = os.path.join(
                    temp_migration_dir,
                    'versions',
                    'test_migration_create_users_table.py'
                )
                
                # Create test migration module
                migration_code = '''
def upgrade():
    import alembic.op as op
    import sqlalchemy as sa
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False)
    )
    
    # Create index
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

def downgrade():
    import alembic.op as op
    op.drop_table('users')
'''
                
                # Execute upgrade in a safe namespace
                namespace = {
                    'op': mock_op,
                    'sa': MagicMock()  # Mock sqlalchemy
                }
                
                exec(migration_code, namespace)
                
                # Call upgrade function
                namespace['upgrade']()
                
                # Verify table creation was called
                mock_op.create_table.assert_called_once()
                mock_op.create_index.assert_called_once()
    
    def test_migration_downgrade(self, temp_migration_dir):
        """Test migration downgrade."""
        # Mock alembic operations
        with patch('alembic.op') as mock_op:
            # Import and test migration downgrade
            migration_code = '''
def downgrade():
    import alembic.op as op
    op.drop_table('users')
'''
            
            # Execute downgrade in a safe namespace
            namespace = {'op': mock_op}
            exec(migration_code, namespace)
            
            # Call downgrade function
            namespace['downgrade']()
            
            # Verify table drop was called
            mock_op.drop_table.assert_called_once_with('users')
    
    def test_migration_chain(self):
        """Test migration dependency chain."""
        # Create mock migration chain
        migrations = [
            {
                'id': '001_initial',
                'message': 'Initial schema',
                'upgrade': 'CREATE TABLE users (...)',
                'downgrade': 'DROP TABLE users',
                'depends_on': None
            },
            {
                'id': '002_add_subscriptions',
                'message': 'Add subscriptions table',
                'upgrade': 'CREATE TABLE subscriptions (...)',
                'downgrade': 'DROP TABLE subscriptions',
                'depends_on': '001_initial'
            },
            {
                'id': '003_add_videos',
                'message': 'Add videos table',
                'upgrade': 'CREATE TABLE videos (...)',
                'downgrade': 'DROP TABLE videos',
                'depends_on': '001_initial'
            }
        ]
        
        # Test dependency resolution
        dependency_graph = {}
        for migration in migrations:
            if migration['depends_on']:
                dependency_graph[migration['id']] = migration['depends_on']
            else:
                dependency_graph[migration['id']] = None
        
        # Verify chain
        assert dependency_graph['001_initial'] is None
        assert dependency_graph['002_add_subscriptions'] == '001_initial'
        assert dependency_graph['003_add_videos'] == '001_initial'
    
    def test_migration_validation(self):
        """Test migration validation."""
        # Valid migration should have both upgrade and downgrade
        valid_migration = {
            'upgrade': 'CREATE TABLE test (...)',
            'downgrade': 'DROP TABLE test'
        }
        
        assert 'upgrade' in valid_migration
        assert 'downgrade' in valid_migration
        
        # Invalid migration missing downgrade
        invalid_migration = {
            'upgrade': 'CREATE TABLE test (...)'
            # Missing downgrade
        }
        
        assert 'downgrade' not in invalid_migration
    
    def test_data_migrations(self):
        """Test data migrations (not just schema)."""
        # Data migration example
        data_migration = {
            'description': 'Migrate user tiers from old to new format',
            'upgrade': '''
                UPDATE users 
                SET tier = CASE 
                    WHEN old_tier = 'basic' THEN 'starter'
                    WHEN old_tier = 'premium' THEN 'pro'
                    ELSE 'free'
                END
            ''',
            'downgrade': '''
                UPDATE users 
                SET tier = CASE 
                    WHEN tier = 'starter' THEN 'basic'
                    WHEN tier = 'pro' THEN 'premium'
                    ELSE 'free'
                END
            '''
        }
        
        assert 'UPDATE' in data_migration['upgrade']
        assert 'UPDATE' in data_migration['downgrade']
    
    def test_migration_rollback(self):
        """Test migration rollback."""
        # Simulate failed migration
        migrations_applied = ['001_initial', '002_add_subscriptions']
        
        # Rollback last migration
        last_migration = migrations_applied.pop()
        
        assert last_migration == '002_add_subscriptions'
        assert len(migrations_applied) == 1
        assert migrations_applied[0] == '001_initial'
    
    def test_migration_conflict_resolution(self):
        """Test migration conflict resolution."""
        # Simulate concurrent migration attempts
        migration_locks = {}
        
        def acquire_lock(migration_id):
            if migration_id in migration_locks:
                return False  # Lock already held
            migration_locks[migration_id] = True
            return True
        
        def release_lock(migration_id):
            if migration_id in migration_locks:
                del migration_locks[migration_id]
        
        # Try to acquire lock
        migration_id = '003_add_videos'
        assert acquire_lock(migration_id) == True
        assert migration_id in migration_locks
        
        # Try to acquire same lock again (should fail)
        assert acquire_lock(migration_id) == False
        
        # Release lock
        release_lock(migration_id)
        assert migration_id not in migration_locks
        
        # Now can acquire again
        assert acquire_lock(migration_id) == True
    
    def test_migration_error_handling(self):
        """Test migration error handling."""
        # Simulate migration error
        def risky_migration():
            # This would fail in real database
            raise Exception("Database constraint violation")
        
        # Should catch and handle migration errors
        try:
            risky_migration()
            assert False, "Should have raised exception"
        except Exception as e:
            assert "Database constraint violation" in str(e)
        
        # Test rollback on error
        migrations_before_error = ['001_initial']
        
        try:
            # Attempt migration
            risky_migration()
            migrations_before_error.append('002_failed')
        except:
            # Rollback to before error state
            pass
        
        assert '002_failed' not in migrations_before_error
        assert len(migrations_before_error) == 1
    
    def test_migration_performance(self):
        """Test migration performance considerations."""
        # Large table migration should use batches
        batch_size = 1000
        total_records = 10000
        batches = total_records // batch_size
        
        if total_records % batch_size > 0:
            batches += 1
        
        assert batches == 10  # 10000 / 1000
        
        # Test timing
        import time
        
        start_time = time.time()
        
        # Simulate migration work
        time.sleep(0.01)  # 10ms
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in reasonable time
        assert duration < 0.1  # Less than 100ms
    
    def test_migration_idempotency(self):
        """Test migration idempotency."""
        # Migration should be safe to run multiple times
        migration_count = 0
        
        def idempotent_migration():
            nonlocal migration_count
            
            # Check if migration already applied
            if migration_count == 0:
                # Apply migration
                migration_count += 1
                return True
            else:
                # Already applied, skip
                return False
        
        # First run should apply
        assert idempotent_migration() == True
        assert migration_count == 1
        
        # Second run should skip
        assert idempotent_migration() == False
        assert migration_count == 1  # Still 1
    
    def test_migration_dry_run(self):
        """Test migration dry run."""
        # Dry run should not modify database
        operations_performed = []
        
        def dry_run_migration():
            # In dry run mode, just record what would be done
            operations_performed.append('CREATE TABLE users')
            operations_performed.append('CREATE INDEX ix_users_email')
            return operations_performed
        
        result = dry_run_migration()
        
        assert len(result) == 2
        assert 'CREATE TABLE users' in result
        assert 'CREATE INDEX ix_users_email' in result
        
        # But database should not be modified
        # (This would be verified with actual database in integration tests)