# Create: enrollments/management/__init__.py (if it doesn't exist)
# Create: enrollments/management/commands/__init__.py (if it doesn't exist)
# Create: enrollments/management/commands/clean_legacy_data.py

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """
    Clean up any legacy data that might conflict with new nationality/residency fields.
    
    This command directly modifies the database to handle any existing data
    that might prevent the new migration from applying successfully.
    
    Usage:
        python manage.py clean_legacy_data --check    # Check for issues
        python manage.py clean_legacy_data --fix      # Fix the issues
    """
    
    help = 'Clean up legacy data before applying nationality/residency migrations'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Check for data issues without making changes',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix the problematic data',
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        
        if options['check']:
            self.check_for_issues()
        elif options['fix']:
            self.fix_issues()
        else:
            self.stdout.write(
                self.style.ERROR('Please specify either --check or --fix')
            )
    
    def check_for_issues(self):
        """Check for data that would cause migration issues"""
        self.stdout.write(
            self.style.SUCCESS('Checking for legacy data issues...')
        )
        
        with connection.cursor() as cursor:
            # Check if nationality/residency columns exist and have problematic data
            table_names = [
                'enrollments_associatedapplication',
                'enrollments_designatedapplication', 
                'enrollments_studentapplication'
            ]
            
            issues_found = False
            
            for table_name in table_names:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, [table_name])
                
                if not cursor.fetchone()[0]:
                    self.stdout.write(f"  Table {table_name} does not exist - OK")
                    continue
                
                # Check if nationality column exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'nationality'
                    );
                """, [table_name])
                
                if cursor.fetchone()[0]:
                    # Check for long nationality values
                    cursor.execute(f"""
                        SELECT nationality, COUNT(*) 
                        FROM {table_name} 
                        WHERE LENGTH(nationality) > 2 
                        GROUP BY nationality;
                    """)
                    
                    long_nationality = cursor.fetchall()
                    if long_nationality:
                        issues_found = True
                        self.stdout.write(
                            self.style.WARNING(
                                f"  {table_name}: Found nationality values > 2 chars:"
                            )
                        )
                        for value, count in long_nationality:
                            self.stdout.write(f"    '{value}': {count} records")
                
                # Check if residency column exists  
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'residency'
                    );
                """, [table_name])
                
                if cursor.fetchone()[0]:
                    # Check for long residency values
                    cursor.execute(f"""
                        SELECT residency, COUNT(*) 
                        FROM {table_name} 
                        WHERE LENGTH(residency) > 2 
                        GROUP BY residency;
                    """)
                    
                    long_residency = cursor.fetchall()
                    if long_residency:
                        issues_found = True
                        self.stdout.write(
                            self.style.WARNING(
                                f"  {table_name}: Found residency values > 2 chars:"
                            )
                        )
                        for value, count in long_residency:
                            self.stdout.write(f"    '{value}': {count} records")
                
                if not issues_found:
                    self.stdout.write(
                        self.style.SUCCESS(f"  {table_name}: No issues found")
                    )
        
        if not issues_found:
            self.stdout.write(
                self.style.SUCCESS('\nNo issues found. Migration should work fine.')
            )
        else:
            self.stdout.write(
                self.style.ERROR('\nIssues found! Run with --fix to resolve them.')
            )
    
    def fix_issues(self):
        """Fix the problematic data"""
        self.stdout.write(
            self.style.SUCCESS('Fixing legacy data issues...')
        )
        
        # Mapping for 3-character codes to 2-character codes
        code_mapping = {
            'SDC': 'SA',  # SADC -> South Africa
            'ANG': 'AO',  # Angola
            'BOT': 'BW',  # Botswana  
            'LES': 'LS',  # Lesotho
            'MAL': 'MW',  # Malawi
            'MAU': 'MU',  # Mauritius
            'MOZ': 'MZ',  # Mozambique
            'NAM': 'NA',  # Namibia
            'SEY': 'SC',  # Seychelles
            'SWA': 'SZ',  # Eswatini (Swaziland)
            'TAN': 'TZ',  # Tanzania
            'ZAI': 'CD',  # Democratic Republic of Congo
            'ZAM': 'ZM',  # Zambia
            'ZIM': 'ZW',  # Zimbabwe
            'AIS': 'AS',  # Asian countries
            'AUS': 'AU',  # Australia & Oceania
            'EUR': 'EU',  # European countries
            'NOR': 'US',  # North American countries
            'SOU': 'BR',  # South & Central American countries
            'ROA': 'AF',  # Rest of Africa
            'OOC': 'OC',  # Other & Rest of Oceania
        }
        
        with connection.cursor() as cursor:
            table_names = [
                'enrollments_associatedapplication',
                'enrollments_designatedapplication', 
                'enrollments_studentapplication'
            ]
            
            total_fixed = 0
            
            for table_name in table_names:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, [table_name])
                
                if not cursor.fetchone()[0]:
                    continue
                
                table_fixed = 0
                
                # Fix nationality field if it exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'nationality'
                    );
                """, [table_name])
                
                if cursor.fetchone()[0]:
                    for old_code, new_code in code_mapping.items():
                        cursor.execute(f"""
                            UPDATE {table_name} 
                            SET nationality = %s 
                            WHERE nationality = %s;
                        """, [new_code, old_code])
                        
                        rows_updated = cursor.rowcount
                        if rows_updated > 0:
                            self.stdout.write(
                                f"  {table_name}: Updated {rows_updated} nationality records "
                                f"'{old_code}' -> '{new_code}'"
                            )
                            table_fixed += rows_updated
                    
                    # Handle any remaining unmapped nationality codes
                    cursor.execute(f"""
                        UPDATE {table_name} 
                        SET nationality = 'U' 
                        WHERE LENGTH(nationality) > 2;
                    """)
                    
                    rows_updated = cursor.rowcount
                    if rows_updated > 0:
                        self.stdout.write(
                            f"  {table_name}: Set {rows_updated} unmapped nationality values to 'U'"
                        )
                        table_fixed += rows_updated
                
                # Fix residency field if it exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'residency'
                    );
                """, [table_name])
                
                if cursor.fetchone()[0]:
                    for old_code, new_code in code_mapping.items():
                        cursor.execute(f"""
                            UPDATE {table_name} 
                            SET residency = %s 
                            WHERE residency = %s;
                        """, [new_code, old_code])
                        
                        rows_updated = cursor.rowcount
                        if rows_updated > 0:
                            self.stdout.write(
                                f"  {table_name}: Updated {rows_updated} residency records "
                                f"'{old_code}' -> '{new_code}'"
                            )
                            table_fixed += rows_updated
                    
                    # Handle any remaining unmapped residency codes
                    cursor.execute(f"""
                        UPDATE {table_name} 
                        SET residency = 'U' 
                        WHERE LENGTH(residency) > 2;
                    """)
                    
                    rows_updated = cursor.rowcount
                    if rows_updated > 0:
                        self.stdout.write(
                            f"  {table_name}: Set {rows_updated} unmapped residency values to 'U'"
                        )
                        table_fixed += rows_updated
                
                if table_fixed == 0:
                    self.stdout.write(f"  {table_name}: No changes needed")
                else:
                    total_fixed += table_fixed
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nFixed {total_fixed} records total. You can now run migrations.'
            )
        )