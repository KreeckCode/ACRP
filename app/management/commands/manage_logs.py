"""
Django Management Command: Manage Application Logs

This command helps you monitor, analyze, and clean up log files.

File Location: app/management/commands/manage_logs.py

Usage:
    python manage.py manage_logs --status        # Show log file status
    python manage.py manage_logs --tail 50       # Show last 50 log lines
    python manage.py manage_logs --errors        # Show recent errors
    python manage.py manage_logs --clean 30      # Delete logs older than 30 days
    python manage.py manage_logs --watch         # Watch logs in real-time
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from pathlib import Path
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict


class Command(BaseCommand):
    help = 'Manage and monitor application log files'

    def add_arguments(self, parser):
        """Define command-line arguments"""
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show status of all log files',
        )
        parser.add_argument(
            '--tail',
            type=int,
            metavar='N',
            help='Show last N lines from main log file',
        )
        parser.add_argument(
            '--errors',
            action='store_true',
            help='Show recent ERROR and CRITICAL level logs',
        )
        parser.add_argument(
            '--clean',
            type=int,
            metavar='DAYS',
            help='Delete log files older than DAYS',
        )
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Watch log file in real-time (like tail -f)',
        )
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Analyze log patterns and show statistics',
        )
        parser.add_argument(
            '--file',
            type=str,
            default='acrp.log',
            help='Specify log file name (default: acrp.log)',
        )

    def handle(self, *args, **options):
        """Main command handler"""
        # Get logs directory
        self.logs_dir = settings.BASE_DIR / 'logs'
        
        # Ensure logs directory exists
        if not self.logs_dir.exists():
            self.stdout.write(
                self.style.ERROR(f'Logs directory does not exist: {self.logs_dir}')
            )
            return

        # Execute requested action
        if options['status']:
            self.show_status()
        elif options['tail']:
            self.tail_logs(options['tail'], options['file'])
        elif options['errors']:
            self.show_errors(options['file'])
        elif options['clean'] is not None:
            self.clean_logs(options['clean'])
        elif options['watch']:
            self.watch_logs(options['file'])
        elif options['analyze']:
            self.analyze_logs(options['file'])
        else:
            self.stdout.write(
                self.style.WARNING('No action specified. Use --help to see options.')
            )
            self.show_status()  # Show status by default

    def show_status(self):
        """Display status of all log files"""
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('LOG FILES STATUS'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))

        log_files = sorted(self.logs_dir.glob('*.log*'))
        
        if not log_files:
            self.stdout.write(self.style.WARNING('No log files found!'))
            return

        total_size = 0
        
        for log_file in log_files:
            stat = log_file.stat()
            size_mb = stat.st_size / 1024 / 1024
            total_size += size_mb
            
            # Get file modification time
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            time_ago = self._humanize_time_delta(datetime.now() - mod_time)
            
            # Determine color based on size
            if size_mb > 50:
                size_style = self.style.ERROR
            elif size_mb > 20:
                size_style = self.style.WARNING
            else:
                size_style = self.style.SUCCESS

            # Format output
            self.stdout.write(f"📄 {log_file.name}")
            self.stdout.write(f"   Size: {size_style(f'{size_mb:.2f} MB')}")
            self.stdout.write(f"   Modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')} ({time_ago} ago)")
            self.stdout.write(f"   Lines: {self._count_lines(log_file):,}")
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(f"\nTotal log size: {total_size:.2f} MB"))
        self.stdout.write(self.style.SUCCESS(f"Number of files: {len(log_files)}"))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))

    def tail_logs(self, num_lines, filename):
        """Show last N lines from log file"""
        log_file = self.logs_dir / filename
        
        if not log_file.exists():
            raise CommandError(f'Log file not found: {log_file}')

        self.stdout.write(
            self.style.SUCCESS(f'\n📋 Last {num_lines} lines from {filename}:\n')
        )
        self.stdout.write('='*70 + '\n')

        try:
            # Read last N lines efficiently
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-num_lines:] if len(lines) > num_lines else lines
                
                for line in last_lines:
                    # Color code based on log level
                    line = line.rstrip()
                    if '[ERROR]' in line or '[CRITICAL]' in line:
                        self.stdout.write(self.style.ERROR(line))
                    elif '[WARNING]' in line:
                        self.stdout.write(self.style.WARNING(line))
                    elif '[INFO]' in line:
                        self.stdout.write(self.style.SUCCESS(line))
                    else:
                        self.stdout.write(line)

        except Exception as e:
            raise CommandError(f'Error reading log file: {e}')

        self.stdout.write('\n' + '='*70 + '\n')

    def show_errors(self, filename):
        """Show recent ERROR and CRITICAL level logs"""
        log_file = self.logs_dir / filename
        
        if not log_file.exists():
            raise CommandError(f'Log file not found: {log_file}')

        self.stdout.write(
            self.style.ERROR(f'\n🔥 Recent errors from {filename}:\n')
        )
        self.stdout.write('='*70 + '\n')

        error_count = 0
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '[ERROR]' in line or '[CRITICAL]' in line:
                        self.stdout.write(self.style.ERROR(line.rstrip()))
                        error_count += 1

        except Exception as e:
            raise CommandError(f'Error reading log file: {e}')

        if error_count == 0:
            self.stdout.write(self.style.SUCCESS('✓ No errors found!'))
        else:
            self.stdout.write(
                self.style.WARNING(f'\nTotal errors found: {error_count}')
            )

        self.stdout.write('\n' + '='*70 + '\n')

    def clean_logs(self, days):
        """Delete log files older than specified days"""
        cutoff_time = datetime.now() - timedelta(days=days)
        
        self.stdout.write(
            self.style.WARNING(
                f'\n🗑️  Cleaning logs older than {days} days (before {cutoff_time.strftime("%Y-%m-%d")})\n'
            )
        )

        deleted_files = []
        total_size = 0

        for log_file in self.logs_dir.glob('*.log*'):
            mod_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            
            if mod_time < cutoff_time:
                size = log_file.stat().st_size
                total_size += size
                deleted_files.append((log_file.name, size))
                
                try:
                    log_file.unlink()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Deleted: {log_file.name} ({size / 1024:.2f} KB)'
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'✗ Failed to delete {log_file.name}: {e}')
                    )

        if deleted_files:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Cleaned {len(deleted_files)} files, freed {total_size / 1024 / 1024:.2f} MB\n'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'\nNo log files older than {days} days found.\n')
            )

    def watch_logs(self, filename):
        """Watch log file in real-time (like tail -f)"""
        log_file = self.logs_dir / filename
        
        if not log_file.exists():
            raise CommandError(f'Log file not found: {log_file}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\n👁️  Watching {filename} in real-time... (Press Ctrl+C to stop)\n'
            )
        )
        self.stdout.write('='*70 + '\n')

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                # Go to end of file
                f.seek(0, 2)
                
                while True:
                    line = f.readline()
                    if line:
                        # Color code based on log level
                        line = line.rstrip()
                        if '[ERROR]' in line or '[CRITICAL]' in line:
                            self.stdout.write(self.style.ERROR(line))
                        elif '[WARNING]' in line:
                            self.stdout.write(self.style.WARNING(line))
                        elif '[INFO]' in line:
                            self.stdout.write(self.style.SUCCESS(line))
                        else:
                            self.stdout.write(line)
                    else:
                        import time
                        time.sleep(0.1)  # Wait a bit before checking again

        except KeyboardInterrupt:
            self.stdout.write('\n\n✓ Stopped watching logs.\n')
        except Exception as e:
            raise CommandError(f'Error watching log file: {e}')

    def analyze_logs(self, filename):
        """Analyze log patterns and show statistics"""
        log_file = self.logs_dir / filename
        
        if not log_file.exists():
            raise CommandError(f'Log file not found: {log_file}')

        self.stdout.write(
            self.style.SUCCESS(f'\n📊 Analyzing {filename}...\n')
        )
        self.stdout.write('='*70 + '\n')

        # Statistics
        level_counts = defaultdict(int)
        module_counts = defaultdict(int)
        hour_counts = defaultdict(int)
        total_lines = 0

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    total_lines += 1
                    
                    # Count by log level
                    if '[DEBUG]' in line:
                        level_counts['DEBUG'] += 1
                    elif '[INFO]' in line:
                        level_counts['INFO'] += 1
                    elif '[WARNING]' in line:
                        level_counts['WARNING'] += 1
                    elif '[ERROR]' in line:
                        level_counts['ERROR'] += 1
                    elif '[CRITICAL]' in line:
                        level_counts['CRITICAL'] += 1
                    
                    # Extract module name (between pipes)
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            module = parts[1].strip()
                            module_counts[module] += 1
                    
                    # Extract hour (for activity patterns)
                    if ']' in line:
                        try:
                            time_part = line.split(']')[1].strip().split()[0]
                            if ':' in time_part:
                                hour = time_part.split(':')[0]
                                hour_counts[hour] += 1
                        except:
                            pass

            # Display statistics
            self.stdout.write(self.style.SUCCESS('📈 Log Level Distribution:'))
            for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                count = level_counts[level]
                percentage = (count / total_lines * 100) if total_lines > 0 else 0
                bar = '█' * int(percentage / 2)
                self.stdout.write(f"  {level:10} : {count:6,} ({percentage:5.1f}%) {bar}")
            
            self.stdout.write(f'\n📦 Top 10 Most Active Modules:')
            for module, count in sorted(module_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                percentage = (count / total_lines * 100) if total_lines > 0 else 0
                self.stdout.write(f"  {module:30} : {count:6,} ({percentage:5.1f}%)")
            
            self.stdout.write(f'\n⏰ Activity by Hour:')
            for hour in sorted(hour_counts.keys()):
                count = hour_counts[hour]
                bar = '█' * min(int(count / 10), 50)
                self.stdout.write(f"  {hour}:00 : {count:6,} {bar}")
            
            self.stdout.write(f'\n📊 Total Statistics:')
            self.stdout.write(f"  Total log entries: {total_lines:,}")
            self.stdout.write(f"  File size: {log_file.stat().st_size / 1024 / 1024:.2f} MB")
            self.stdout.write(f"  Unique modules: {len(module_counts)}")
            
        except Exception as e:
            raise CommandError(f'Error analyzing log file: {e}')

        self.stdout.write('\n' + '='*70 + '\n')

    def _humanize_time_delta(self, delta):
        """Convert timedelta to human-readable format"""
        seconds = int(delta.total_seconds())
        
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            return f"{seconds // 60} minutes"
        elif seconds < 86400:
            return f"{seconds // 3600} hours"
        else:
            return f"{seconds // 86400} days"

    def _count_lines(self, file_path):
        """Count number of lines in file efficiently"""
        try:
            with open(file_path, 'rb') as f:
                return sum(1 for _ in f)
        except:
            return 0