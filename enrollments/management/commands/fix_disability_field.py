# Create: enrollments/management/commands/fix_disability_field.py

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    """
    Fix disability field data that's preventing the migration.
    
    The migration is failing because existing disability field data
    is longer than 2 characters, but the new model definition 
    restricts it to max_length=2.
    """
    
    help = 'Fix disability field data for migration'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Check for disability field issues',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Fix the disability field issues',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
    
    def handle(self, *args, **options):
        """Main command handler"""
        
        if options['check']:
            self.check_disability_data()
        elif options['fix']:
            self.fix_disability_data(dry_run=options['dry_run'])
        else:
            self.stdout.write(
                self.style.ERROR('Please specify either --check or --fix')
            )
    
    def check_disability_data(self):
        """Check for problematic disability field data"""
        self.stdout.write(
            self.style.SUCCESS('Checking disability field data...\n')
        )
        
        with connection.cursor() as cursor:
            application_tables = [
                'enrollments_associatedapplication',
                'enrollments_designatedapplication', 
                'enrollments_studentapplication'
            ]
            
            issues_found = False
            
            for table_name in application_tables:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, [table_name])
                
                if not cursor.fetchone()[0]:
                    self.stdout.write(f"⚠️  Table {table_name} does not exist")
                    continue
                
                # Check if disability column exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'disability'
                    );
                """, [table_name])
                
                if not cursor.fetchone()[0]:
                    self.stdout.write(f"⚠️  {table_name}: disability column does not exist")
                    continue
                
                self.stdout.write(f"🔍 Checking {table_name}:")
                
                # Get disability column info
                cursor.execute("""
                    SELECT data_type, character_maximum_length
                    FROM information_schema.columns 
                    WHERE table_name = %s AND column_name = 'disability';
                """, [table_name])
                
                col_info = cursor.fetchone()
                if col_info:
                    data_type, max_length = col_info
                    self.stdout.write(f"  📋 Current disability column: {data_type}({max_length})")
                
                # Check for long disability values
                cursor.execute(f"""
                    SELECT disability, LENGTH(disability) as len, COUNT(*) as count
                    FROM {table_name} 
                    WHERE LENGTH(disability) > 2 AND disability IS NOT NULL
                    GROUP BY disability, LENGTH(disability)
                    ORDER BY LENGTH(disability) DESC, COUNT(*) DESC;
                """)
                
                long_values = cursor.fetchall()
                
                if long_values:
                    issues_found = True
                    self.stdout.write(f"  ❌ Found disability values longer than 2 characters:")
                    for value, length, count in long_values:
                        self.stdout.write(f"    '{value}' (length {length}): {count} records")
                else:
                    self.stdout.write(f"  ✅ No problematic disability values found")
                
                # Show all unique disability values for context
                cursor.execute(f"""
                    SELECT disability, COUNT(*) as count, LENGTH(disability) as len
                    FROM {table_name} 
                    WHERE disability IS NOT NULL
                    GROUP BY disability, LENGTH(disability)
                    ORDER BY COUNT(*) DESC;
                """)
                
                all_values = cursor.fetchall()
                if all_values:
                    self.stdout.write(f"  📊 All unique disability values:")
                    for value, count, length in all_values:
                        status = "❌" if length > 2 else "✅"
                        self.stdout.write(f"    {status} '{value}' (len {length}): {count} records")
                
                self.stdout.write("")
            
            if not issues_found:
                self.stdout.write(
                    self.style.SUCCESS('✅ No disability field issues found. Migration should work fine.')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('❌ Issues found! Run with --fix to resolve them.')
                )
    
    def fix_disability_data(self, dry_run=False):
        """Fix problematic disability field data"""
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made\n')
            )
        
        self.stdout.write(
            self.style.SUCCESS('Fixing disability field data...\n')
        )
        
        # Mapping for common disability values to SAQA-compliant codes
        disability_mapping = {
            # Common long values to proper SAQA codes
            'None': 'N',
            'NONE': 'N',
            'none': 'N',
            'No': 'N',
            'NO': 'N',
            'no': 'N',
            'N/A': 'N',
            'n/a': 'N',
            'Not applicable': 'N',
            'NOT APPLICABLE': 'N',
            'not applicable': 'N',
            
            # Sight-related
            'Sight': '01',
            'SIGHT': '01',
            'sight': '01',
            'Visual': '01',
            'VISUAL': '01',
            'visual': '01',
            'Blind': '01',
            'BLIND': '01',
            'blind': '01',
            'Vision': '01',
            'VISION': '01',
            'vision': '01',
            
            # Hearing-related  
            'Hearing': '02',
            'HEARING': '02',
            'hearing': '02',
            'Deaf': '02',
            'DEAF': '02',
            'deaf': '02',
            
            # Communication-related
            'Communication': '03',
            'COMMUNICATION': '03',
            'communication': '03',
            'Speech': '03',
            'SPEECH': '03',
            'speech': '03',
            
            # Physical-related
            'Physical': '04',
            'PHYSICAL': '04',
            'physical': '04',
            'Mobility': '04',
            'MOBILITY': '04',
            'mobility': '04',
            
            # Intellectual-related
            'Intellectual': '05',
            'INTELLECTUAL': '05',
            'intellectual': '05',
            'Learning': '05',
            'LEARNING': '05',
            'learning': '05',
            'Mental': '05',
            'MENTAL': '05',
            'mental': '05',
            
            # Emotional/behavioral
            'Emotional': '06',
            'EMOTIONAL': '06',
            'emotional': '06',
            'Psychological': '06',
            'PSYCHOLOGICAL': '06',
            'psychological': '06',
            'Behavioral': '06',
            'BEHAVIORAL': '06',
            'behavioral': '06',
            'Behaviour': '06',
            'BEHAVIOUR': '06',
            'behaviour': '06',
            
            # Multiple
            'Multiple': '07',
            'MULTIPLE': '07',
            'multiple': '07',
            
            # Unspecified
            'Unspecified': '09',
            'UNSPECIFIED': '09',
            'unspecified': '09',
            'Other': '09',
            'OTHER': '09',
            'other': '09',
            'Unknown': '09',
            'UNKNOWN': '09',
            'unknown': '09',
        }
        
        with connection.cursor() as cursor:
            application_tables = [
                'enrollments_associatedapplication',
                'enrollments_designatedapplication', 
                'enrollments_studentapplication'
            ]
            
            total_fixed = 0
            
            for table_name in application_tables:
                # Check if table and column exist
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = %s AND column_name = 'disability'
                    );
                """, [table_name])
                
                if not cursor.fetchone()[0]:
                    continue
                
                self.stdout.write(f"🔧 Processing {table_name}:")
                table_fixed = 0
                
                # Apply mappings
                for old_value, new_value in disability_mapping.items():
                    if dry_run:
                        cursor.execute(f"""
                            SELECT COUNT(*) FROM {table_name} 
                            WHERE disability = %s;
                        """, [old_value])
                        count = cursor.fetchone()[0]
                        if count > 0:
                            self.stdout.write(f"  Would change '{old_value}' -> '{new_value}' ({count} records)")
                            table_fixed += count
                    else:
                        cursor.execute(f"""
                            UPDATE {table_name} 
                            SET disability = %s 
                            WHERE disability = %s;
                        """, [new_value, old_value])
                        
                        rows_updated = cursor.rowcount
                        if rows_updated > 0:
                            self.stdout.write(f"  Changed '{old_value}' -> '{new_value}' ({rows_updated} records)")
                            table_fixed += rows_updated
                
                # Handle any remaining unmapped values longer than 2 characters
                if dry_run:
                    cursor.execute(f"""
                        SELECT disability, COUNT(*) FROM {table_name} 
                        WHERE LENGTH(disability) > 2 AND disability IS NOT NULL
                        GROUP BY disability;
                    """)
                    remaining = cursor.fetchall()
                    for value, count in remaining:
                        if value not in disability_mapping:
                            self.stdout.write(f"  Would change unmapped '{value}' -> 'N' ({count} records)")
                            table_fixed += count
                else:
                    cursor.execute(f"""
                        SELECT disability, COUNT(*) FROM {table_name} 
                        WHERE LENGTH(disability) > 2 AND disability IS NOT NULL
                        GROUP BY disability;
                    """)
                    remaining = cursor.fetchall()
                    
                    for value, count in remaining:
                        if value not in disability_mapping:
                            cursor.execute(f"""
                                UPDATE {table_name} 
                                SET disability = 'N' 
                                WHERE disability = %s;
                            """, [value])
                            
                            self.stdout.write(f"  Changed unmapped '{value}' -> 'N' ({count} records)")
                            table_fixed += count
                
                if table_fixed == 0:
                    self.stdout.write(f"  ✅ No changes needed for {table_name}")
                else:
                    total_fixed += table_fixed
                
                self.stdout.write("")
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'DRY RUN: Would fix {total_fixed} disability records total')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Fixed {total_fixed} disability records total')
            )