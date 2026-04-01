"""
Migration script to help move data from SQLite to PostgreSQL
Usage: python migrate_db.py [--source-path PATH] [--target-url URL]
"""

import os
import argparse
import pandas as pd
from sqlalchemy import inspect, create_engine
from db_config import DatabaseConfig
from datetime import datetime

def migrate_sqlite_to_postgres(
    sqlite_path: str = "munder_difflin.db",
    postgres_url: str = None
) -> bool:
    """
    Migrate data from SQLite to PostgreSQL
    
    Args:
        sqlite_path: Path to SQLite database
        postgres_url: PostgreSQL connection URL
        
    Returns:
        True if successful, False otherwise
    """
    
    print(f"Starting migration at {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Validate SQLite database exists
    if not os.path.exists(sqlite_path):
        print(f"ERROR: SQLite database not found at {sqlite_path}")
        return False
    
    try:
        # Create engines
        print("\n1. Connecting to source (SQLite)...")
        sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
        
        print("2. Connecting to target (PostgreSQL)...")
        if postgres_url:
            postgres_engine = create_engine(postgres_url)
        else:
            postgres_engine = DatabaseConfig.get_engine()
            if "sqlite" in str(postgres_engine.url):
                print("ERROR: Target database is also SQLite. Set DATABASE_URL or configure PostgreSQL")
                return False
        
        # Test connections
        print("3. Testing connections...")
        with sqlite_engine.connect() as conn:
            conn.execute("SELECT 1")
        print("   ✓ SQLite connection OK")
        
        with postgres_engine.connect() as conn:
            conn.execute("SELECT 1")
        print("   ✓ PostgreSQL connection OK")
        
        # Get table names
        print("\n4. Analyzing tables...")
        inspector = inspect(sqlite_engine)
        tables = inspector.get_table_names()
        print(f"   Found {len(tables)} tables: {', '.join(tables)}")
        
        # Migrate tables
        print("\n5. Starting data migration...")
        
        total_rows = 0
        for table_name in tables:
            try:
                print(f"\n   Migrating table: {table_name}")
                
                # Read from SQLite
                df = pd.read_sql_table(table_name, sqlite_engine)
                row_count = len(df)
                total_rows += row_count
                
                # Display schema
                print(f"      Columns: {', '.join(df.columns)}")
                print(f"      Rows: {row_count}")
                print(f"      Data types: {dict(df.dtypes)}")
                
                # Write to PostgreSQL
                df.to_sql(table_name, postgres_engine, if_exists="replace", index=False)
                print(f"      ✓ Successfully migrated {row_count} rows")
                
            except Exception as e:
                print(f"      ✗ Error migrating table {table_name}: {str(e)}")
                return False
        
        print("\n" + "=" * 60)
        print(f"✓ Migration successful!")
        print(f"  Total tables: {len(tables)}")
        print(f"  Total rows: {total_rows}")
        print(f"  Completed at: {datetime.now().isoformat()}")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: Migration failed with exception: {str(e)}")
        return False


def verify_migration(
    sqlite_path: str = "munder_difflin.db",
    postgres_url: str = None
) -> bool:
    """
    Verify that migration was successful
    
    Args:
        sqlite_path: Path to SQLite database
        postgres_url: PostgreSQL connection URL
        
    Returns:
        True if verification passes
    """
    
    print("\nVerifying migration...")
    print("-" * 60)
    
    try:
        sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
        postgres_engine = create_engine(postgres_url) if postgres_url else DatabaseConfig.get_engine()
        
        # Compare tables
        sqlite_inspector = inspect(sqlite_engine)
        postgres_inspector = inspect(postgres_engine)
        
        sqlite_tables = set(sqlite_inspector.get_table_names())
        postgres_tables = set(postgres_inspector.get_table_names())
        
        print(f"\nTables in SQLite: {len(sqlite_tables)}")
        print(f"Tables in PostgreSQL: {len(postgres_tables)}")
        
        # Check for missing tables
        missing_tables = sqlite_tables - postgres_tables
        if missing_tables:
            print(f"✗ Missing tables in PostgreSQL: {missing_tables}")
            return False
        
        # Compare row counts
        print("\nRow count comparison:")
        all_match = True
        
        for table_name in sqlite_tables:
            sqlite_count = pd.read_sql(f"SELECT COUNT(*) as count FROM {table_name}", sqlite_engine).iloc[0, 0]
            postgres_count = pd.read_sql(f"SELECT COUNT(*) as count FROM {table_name}", postgres_engine).iloc[0, 0]
            
            match = "✓" if sqlite_count == postgres_count else "✗"
            print(f"  {match} {table_name}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
            
            if sqlite_count != postgres_count:
                all_match = False
        
        if all_match:
            print("\n✓ Verification successful - data matches!")
            return True
        else:
            print("\n✗ Verification failed - data mismatch!")
            return False
            
    except Exception as e:
        print(f"✗ Verification failed with exception: {str(e)}")
        return False


def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite to PostgreSQL"
    )
    
    parser.add_argument(
        "--source-path",
        default="munder_difflin.db",
        help="Path to SQLite database (default: munder_difflin.db)"
    )
    
    parser.add_argument(
        "--target-url",
        help="PostgreSQL connection URL (e.g., postgresql://user:pass@host/db)"
    )
    
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing migration without migrating"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually migrating"
    )
    
    args = parser.parse_args()
    
    print(f"Paper Supply Database Migration Tool")
    print(f"=" * 60)
    
    if args.verify_only:
        success = verify_migration(args.source_path, args.target_url)
    else:
        if args.dry_run:
            print("\nDRY RUN MODE - No changes will be made\n")
            
            sqlite_engine = create_engine(f"sqlite:///{args.source_path}")
            inspector = inspect(sqlite_engine)
            tables = inspector.get_table_names()
            
            print(f"Tables to migrate: {len(tables)}")
            for table_name in tables:
                df = pd.read_sql_table(table_name, sqlite_engine)
                print(f"  - {table_name}: {len(df)} rows, columns: {list(df.columns)}")
            
            print("\nDRY RUN complete. Use without --dry-run to perform actual migration.")
        else:
            success = migrate_sqlite_to_postgres(args.source_path, args.target_url)
            
            if success:
                verify = input("\nVerify migration? (y/n): ").lower() == 'y'
                if verify:
                    verify_migration(args.source_path, args.target_url)


if __name__ == "__main__":
    main()
