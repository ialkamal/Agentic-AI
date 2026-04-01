"""
Database configuration module
Supports both SQLite (local development) and PostgreSQL (cloud production)
"""

import os
from sqlalchemy import create_engine, Engine
from typing import Optional

# =========================================================
# DATABASE CONFIGURATION
# =========================================================

class DatabaseConfig:
    """Manages database configuration based on environment"""
    
    @staticmethod
    def get_engine() -> Engine:
        """
        Get SQLAlchemy engine based on environment settings
        
        Environment variables:
            DATABASE_URL: Full database URL (takes precedence)
            DB_TYPE: 'sqlite' or 'postgres' (default: 'sqlite')
            DB_HOST: Postgres host
            DB_PORT: Postgres port (default: 5432)
            DB_USER: Postgres user
            DB_PASSWORD: Postgres password
            DB_NAME: Database name
        
        Returns:
            SQLAlchemy Engine
        """
        
        # Check if full DATABASE_URL is provided (common in cloud platforms)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return create_engine(database_url, echo=False, pool_pre_ping=True)
        
        # Otherwise, build from individual components
        db_type = os.getenv("DB_TYPE", "sqlite").lower()
        
        if db_type == "postgres":
            return DatabaseConfig._get_postgres_engine()
        else:
            return DatabaseConfig._get_sqlite_engine()
    
    @staticmethod
    def _get_sqlite_engine() -> Engine:
        """Get SQLite engine for local development"""
        db_path = os.getenv("SQLITE_PATH", "munder_difflin.db")
        db_url = f"sqlite:///{db_path}"
        print(f"Using SQLite database: {db_path}")
        return create_engine(db_url, echo=False)
    
    @staticmethod
    def _get_postgres_engine() -> Engine:
        """Get PostgreSQL engine for production"""
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "")
        db_name = os.getenv("DB_NAME", "paper_supplies")
        
        # Build connection string
        if password:
            db_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
        else:
            db_url = f"postgresql://{user}@{host}:{port}/{db_name}"
        
        print(f"Using PostgreSQL database: {db_name} on {host}:{port}")
        
        return create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600    # Recycle connections after 1 hour
        )
    
    @staticmethod
    def is_postgres() -> bool:
        """Check if using PostgreSQL"""
        database_url = os.getenv("DATABASE_URL", "").lower()
        db_type = os.getenv("DB_TYPE", "sqlite").lower()
        
        return "postgres" in database_url or db_type == "postgres"
    
    @staticmethod
    def is_local() -> bool:
        """Check if running in local/development mode"""
        return not DatabaseConfig.is_postgres()


# =========================================================
# MIGRATION HELPERS
# =========================================================

def migrate_sqlite_to_postgres(sqlite_path: str, postgres_engine: Engine) -> None:
    """
    Migrate data from SQLite to PostgreSQL
    
    Args:
        sqlite_path: Path to SQLite database file
        postgres_engine: SQLAlchemy engine for target PostgreSQL database
    """
    import pandas as pd
    from sqlalchemy import inspect
    
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    
    # Get all table names from SQLite
    inspector = inspect(sqlite_engine)
    tables = inspector.get_table_names()
    
    print(f"Migrating {len(tables)} tables from SQLite to PostgreSQL...")
    
    for table_name in tables:
        try:
            # Read from SQLite
            df = pd.read_sql_table(table_name, sqlite_engine)
            
            # Write to PostgreSQL
            df.to_sql(table_name, postgres_engine, if_exists="replace", index=False)
            print(f"✓ Migrated table: {table_name} ({len(df)} rows)")
        except Exception as e:
            print(f"✗ Error migrating table {table_name}: {str(e)}")
    
    print("Migration complete!")


if __name__ == "__main__":
    # Test configuration
    engine = DatabaseConfig.get_engine()
    print(f"Database engine: {engine}")
    print(f"Is PostgreSQL: {DatabaseConfig.is_postgres()}")
    print(f"Is Local: {DatabaseConfig.is_local()}")
