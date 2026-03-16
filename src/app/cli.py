"""CLI commands for the application."""

import click
from flask.cli import with_appcontext
import os
import json
from pathlib import Path
from datetime import datetime

from services.user_service import UserService
from services.tier_service import TierService

# Import the actual task functions from cleanup_tasks
from tasks.cleanup_tasks import cleanup_expired_data, cleanup_temporary_files
from core.logging import setup_logging

# Initialize services
user_service = UserService()
tier_service = TierService()


@click.group()
def cli():
    """Video AI Studio CLI."""
    pass


@cli.command()
@click.option("--email", prompt=True, help="User email")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="User password",
)
@click.option(
    "--tier",
    default="free",
    type=click.Choice(["free", "starter", "pro", "plus", "enterprise"]),
    help="User tier",
)
@click.option("--admin", is_flag=True, help="Make user an admin")
@with_appcontext
def create_user_command(email, password, tier, admin):
    """Create a new user."""
    try:
        user = user_service.create_user(email, password, tier, is_admin=admin)
        click.echo(f"✅ User created successfully:")
        click.echo(f"   ID: {user.id}")
        click.echo(f"   Email: {user.email}")
        click.echo(f"   Tier: {user.tier}")
        click.echo(f'   Admin: {getattr(user, "is_admin", False)}')
    except Exception as e:
        click.echo(f"❌ Error creating user: {str(e)}", err=True)


@cli.command()
@click.option("--user-id", prompt=True, help="User ID")
@click.option(
    "--tier",
    prompt=True,
    type=click.Choice(["free", "starter", "pro", "plus", "enterprise"]),
    help="New tier",
)
@with_appcontext
def upgrade_tier(user_id, tier):
    """Upgrade a user's tier."""
    user = user_service.get_user_by_id(user_id)
    if not user:
        click.echo(f"❌ User not found: {user_id}", err=True)
        return

    try:
        updated_user = user_service.update_user_tier(user_id, tier)
        click.echo(f"✅ User tier upgraded:")
        click.echo(f"   User: {updated_user.email}")
        click.echo(f"   New Tier: {updated_user.tier}")

        # Get monthly limit from tier service
        tier_info = tier_service.get_tier_info(tier)
        if tier_info:
            click.echo(
                f'   Monthly Limit: {tier_info.get("monthly_videos", "N/A")} videos'
            )
    except Exception as e:
        click.echo(f"❌ Error upgrading tier: {str(e)}", err=True)


@cli.command()
@click.option("--days", default=30, help="Days of data to keep")
@with_appcontext
def cleanup(days):
    """Clean up expired videos and temporary files."""
    try:
        # Call the cleanup_expired_data task
        result = cleanup_expired_data.delay(days)
        click.echo(f"✅ Cleanup task scheduled: {result.id}")
        click.echo(f"   Check logs for results")
    except Exception as e:
        click.echo(f"❌ Error during cleanup: {str(e)}", err=True)


@cli.command()
@with_appcontext
def cleanup_temp():
    """Clean up temporary files."""
    try:
        # Call the cleanup_temporary_files task
        result = cleanup_temporary_files.delay()
        click.echo(f"✅ Temporary files cleanup task scheduled: {result.id}")
    except Exception as e:
        click.echo(f"❌ Error during temp cleanup: {str(e)}", err=True)


@cli.command()
@click.option("--output", default="stats.json", help="Output file")
@with_appcontext
def stats(output):
    """Generate system statistics."""
    from providers.firebase_provider import FirebaseProvider

    # Get database provider
    db = FirebaseProvider()

    try:
        # Helper function to count documents
        def count_docs(collection, filters=None):
            try:
                if filters:
                    return len(db.query(collection, filters))
                else:
                    return len(db.get_all(collection))
            except:
                return 0

        stats_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "users": {
                "total": count_docs("users"),
                "by_tier": {
                    "free": count_docs("users", {"tier": "free"}),
                    "starter": count_docs("users", {"tier": "starter"}),
                    "pro": count_docs("users", {"tier": "pro"}),
                    "plus": count_docs("users", {"tier": "plus"}),
                    "enterprise": count_docs("users", {"tier": "enterprise"}),
                },
                "active": count_docs("users", {"is_active": True}),
            },
            "videos": {
                "total": count_docs("videos"),
                "by_status": {
                    "completed": count_docs("videos", {"status": "completed"}),
                    "processing": count_docs("videos", {"status": "processing"}),
                    "failed": count_docs("videos", {"status": "failed"}),
                },
                "by_tier": {
                    "free": count_docs("videos", {"processed_tier": "free"}),
                    "starter": count_docs("videos", {"processed_tier": "starter"}),
                    "pro": count_docs("videos", {"processed_tier": "pro"}),
                    "plus": count_docs("videos", {"processed_tier": "plus"}),
                },
            },
            "processing": {
                "total_jobs": count_docs("processing_jobs"),
                "active_jobs": count_docs("processing_jobs", {"status": "processing"}),
            },
        }

        # Write to file
        with open(output, "w") as f:
            json.dump(stats_data, f, indent=2)

        click.echo(f"✅ Statistics saved to {output}")

        # Print summary
        click.echo("\n📊 System Statistics:")
        click.echo(f'   Total Users: {stats_data["users"]["total"]}')
        click.echo(f'   Total Videos: {stats_data["videos"]["total"]}')
        click.echo(
            f'   Completed Videos: {stats_data["videos"]["by_status"]["completed"]}'
        )
        click.echo(
            f'   Active Processing Jobs: {stats_data["processing"]["active_jobs"]}'
        )

    except Exception as e:
        click.echo(f"❌ Error generating statistics: {str(e)}", err=True)


@cli.command()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Log level",
)
@with_appcontext
def setup_logging_command(log_level):
    """Set up logging configuration."""
    setup_logging(log_level)
    click.echo(f"✅ Logging configured with level: {log_level}")


@cli.command()
@click.confirmation_option(prompt="Are you sure you want to reset the database?")
@with_appcontext
def reset_db():
    """Reset the database (development only)."""
    from providers.firebase_provider import FirebaseProvider

    if os.getenv("FLASK_ENV") != "development":
        click.echo("❌ This command can only be run in development mode", err=True)
        return

    try:
        db = FirebaseProvider()

        # Collections to reset
        collections = [
            "users",
            "videos",
            "processing_jobs",
            "subscriptions",
            "credit_transactions",
            "api_logs",
        ]

        for collection in collections:
            # Delete all documents
            try:
                docs = db.get_all(collection)
                for doc in docs:
                    db.delete(collection, doc["id"])
                click.echo(f"   Cleared {collection}")
            except:
                click.echo(f"   Skipped {collection} (may not exist)")

        click.echo("✅ Database reset completed")

    except Exception as e:
        click.echo(f"❌ Error resetting database: {str(e)}", err=True)


def register_cli_commands(app):
    """Register all CLI commands with Flask app."""
    app.cli.add_command(create_user_command)
    app.cli.add_command(upgrade_tier)
    app.cli.add_command(cleanup)
    app.cli.add_command(cleanup_temp)
    app.cli.add_command(stats)
    app.cli.add_command(setup_logging_command)
    app.cli.add_command(reset_db)
