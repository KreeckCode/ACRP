# Create: enrollments/management/commands/inspect_db_schema.py

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """
    Inspect the actual database schema and data to understand what's causing the migration failure.
    
    This command directly queries the database to see:
    1. What tables exist
    2. What columns exist in each table
    3. What data is in nationality/residency columns
    4. Column constraints and sizes
    """
    
    help = 'Inspect database schema and data for debugging migration issues'
    
    def handle(self, *args, **options):
        """Main command handler"""
        self.stdout.write(
            self.style.SUCCESS('Inspecting database schema and data...\n')
        )
        
        with connection.cursor() as cursor:
            # List all tables that start with enrollments_
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name LIKE 'enrollments_%' 
                AND table_schema = 'public'
                ORDER BY table_name;
            """)
            
            tables = cursor.fetchall()
            self.stdout.write(f"Found {len(tables)} enrollment tables:")
            for table in tables:
                self.stdout.write(f"  - {table[0]}")
            
            self.stdout.write("\n" + "="*60 + "\n")
            
            # Check each application table specifically
            application_tables = [
                'enrollments_associatedapplication',
                'enrollments_designatedapplication', 
                'enrollments_studentapplication'
            ]
            
            for table_name in application_tables:
                self.inspect_table(cursor, table_name)
    
    def inspect_table(self, cursor, table_name):
        """Inspect a specific table"""
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, [table_name])
        
        if not cursor.fetchone()[0]:
            self.stdout.write(f"❌ Table {table_name} does not exist\n")
            return
        
        self.stdout.write(f"🔍 Inspecting {table_name}")
        self.stdout.write("-" * len(f"🔍 Inspecting {table_name}"))
        
        # Get column information
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = %s 
            AND column_name IN ('nationality', 'residency')
            ORDER BY column_name;
        """, [table_name])
        
        columns = cursor.fetchall()
        
        if not columns:
            self.stdout.write("  ❌ No nationality/residency columns found")
        else:
            self.stdout.write("  📋 Column Information:")
            for col_name, data_type, max_length, nullable, default in columns:
                self.stdout.write(f"    - {col_name}: {data_type}({max_length}), nullable={nullable}, default={default}")
        
        # Check for data in these columns if they exist
        for col_name, _, max_length, _, _ in columns:
            self.stdout.write(f"\n  📊 Data in {col_name} column:")
            
            # Get count of records
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {col_name} IS NOT NULL;")
            total_records = cursor.fetchone()[0]
            
            if total_records == 0:
                self.stdout.write("    ✅ No data found")
                continue
            
            self.stdout.write(f"    Total records with data: {total_records}")
            
            # Get unique values and their counts
            cursor.execute(f"""
                SELECT {col_name}, COUNT(*), LENGTH({col_name}) as len
                FROM {table_name} 
                WHERE {col_name} IS NOT NULL 
                GROUP BY {col_name}, LENGTH({col_name})
                ORDER BY LENGTH({col_name}) DESC, COUNT(*) DESC;
            """)
            
            values = cursor.fetchall()
            
            # Show problematic values first (length > 2)
            problematic_values = [v for v in values if v[2] > 2]
            if problematic_values:
                self.stdout.write(f"    ❌ VALUES LONGER THAN 2 CHARACTERS:")
                for value, count, length in problematic_values:
                    self.stdout.write(f"      '{value}' (length {length}): {count} records")
            
            # Show all values
            self.stdout.write(f"    📝 All unique values:")
            for value, count, length in values:
                status = "❌" if length > 2 else "✅"
                self.stdout.write(f"      {status} '{value}' (len {length}): {count} records")
        
        # Get total record count for table
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        total_rows = cursor.fetchone()[0]
        self.stdout.write(f"\n  📈 Total rows in table: {total_rows}")
        
        self.stdout.write("\n")
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--table',
            type=str,
            help='Inspect specific table only',
        )