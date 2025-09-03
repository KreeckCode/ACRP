# Create: enrollments/management/commands/force_fix_data.py

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """
    Force fix any data issues that are preventing migrations.
    
    This command uses aggressive tactics to find and fix ALL data
    that could be causing the VARCHAR(2) constraint violation.
    """
    
    help = 'Aggressively fix all data issues preventing migration'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Apply changes without confirmation',
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made\n')
            )
        
        self.stdout.write(
            self.style.SUCCESS('Aggressively fixing data issues...\n')
        )
        
        with connection.cursor() as cursor:
            # Get all tables in the database
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name LIKE 'enrollments_%' 
                AND table_schema = 'public'
                ORDER BY table_name;
            """)
            
            tables = [row[0] for row in cursor.fetchall()]
            
            total_fixed = 0
            
            for table_name in tables:
                fixed_count = self.fix_table_data(cursor, table_name, dry_run, force)
                total_fixed += fixed_count
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'\nDRY RUN: Would fix {total_fixed} issues total')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\nFixed {total_fixed} issues total')
            )
    
    def fix_table_data(self, cursor, table_name, dry_run=False, force=False):
        """Fix data in a specific table"""
        
        # Check if table has nationality or residency columns
        cursor.execute("""
            SELECT column_name, character_maximum_length
            FROM information_schema.columns 
            WHERE table_name = %s 
            AND column_name IN ('nationality', 'residency')
            ORDER BY column_name;
        """, [table_name])
        
        columns = cursor.fetchall()
        
        if not columns:
            return 0
        
        self.stdout.write(f"Checking {table_name}...")
        
        fixed_count = 0
        
        for column_name, max_length in columns:
            # Find all records with values longer than 2 characters
            cursor.execute(f"""
                SELECT id, {column_name}, LENGTH({column_name}) as len
                FROM {table_name} 
                WHERE LENGTH({column_name}) > 2
                ORDER BY LENGTH({column_name}) DESC;
            """)
            
            problematic_records = cursor.fetchall()
            
            if not problematic_records:
                continue
            
            self.stdout.write(f"  Found {len(problematic_records)} problematic {column_name} values:")
            
            # Mapping for common 3+ character codes to 2-character codes
            code_mapping = {
                'SDC': 'SA', 'SADC': 'SA',
                'ANG': 'AO', 'ANGOLA': 'AO',
                'BOT': 'BW', 'BOTSWANA': 'BW',
                'LES': 'LS', 'LESOTHO': 'LS',
                'MAL': 'MW', 'MALAWI': 'MW',
                'MAU': 'MU', 'MAURITIUS': 'MU',
                'MOZ': 'MZ', 'MOZAMBIQUE': 'MZ',
                'NAM': 'NA', 'NAMIBIA': 'NA',
                'SEY': 'SC', 'SEYCHELLES': 'SC',
                'SWA': 'SZ', 'SWAZILAND': 'SZ', 'ESWATINI': 'SZ',
                'TAN': 'TZ', 'TANZANIA': 'TZ',
                'ZAI': 'CD', 'ZAIRE': 'CD', 'CONGO': 'CD',
                'ZAM': 'ZM', 'ZAMBIA': 'ZM',
                'ZIM': 'ZW', 'ZIMBABWE': 'ZW',
                'AIS': 'AS', 'ASIAN': 'AS', 'ASIA': 'AS',
                'AUS': 'AU', 'AUSTRALIA': 'AU', 'OCEANIA': 'AU',
                'EUR': 'EU', 'EUROPE': 'EU', 'EUROPEAN': 'EU',
                'NOR': 'US', 'NORTH_AMERICA': 'US', 'AMERICA': 'US',
                'SOU': 'BR', 'SOUTH_AMERICA': 'BR',
                'ROA': 'AF', 'AFRICA': 'AF',
                'OOC': 'OC', 'OTHER': 'U',
                'UNSPECIFIED': 'U', 'UNKNOWN': 'U', 'NULL': 'U',
            }
            
            for record_id, value, length in problematic_records:
                # Try to map the value
                new_value = code_mapping.get(value.upper(), 'U')
                
                self.stdout.write(f"    ID {record_id}: '{value}' (len {length}) -> '{new_value}'")
                
                if not dry_run:
                    cursor.execute(f"""
                        UPDATE {table_name} 
                        SET {column_name} = %s 
                        WHERE id = %s;
                    """, [new_value, record_id])
                
                fixed_count += 1
        
        if fixed_count > 0 and not dry_run:
            self.stdout.write(f"  Fixed {fixed_count} records in {table_name}")
        
        return fixed_count