from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from django.core import serializers
import os
import sys
import gzip
import shutil
import subprocess
import boto3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create database and media files backup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            help='Directory to store backups'
        )
        
        parser.add_argument(
            '--keep-local',
            type=int,
            default=7,
            help='Number of local backup copies to keep'
        )
        
        parser.add_argument(
            '--upload-s3',
            action='store_true',
            help='Upload backup to S3'
        )
        
        parser.add_argument(
            '--s3-bucket',
            type=str,
            help='S3 bucket name for backup storage'
        )
        
        parser.add_argument(
            '--backup-media',
            action='store_true',
            help='Include media files in backup'
        )
        
        parser.add_argument(
            '--notification-email',
            type=str,
            help='Email to notify about backup status'
        )

    def handle(self, *args, **options):
        try:
            # Set up logging
            self.setup_logging()
            
            # Create backup directory if it doesn't exist
            backup_dir = options.get('output_dir') or os.path.join(settings.BASE_DIR, 'backups')
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            # Generate backup timestamp
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            
            # Perform database backup
            db_backup_path = self.backup_database(backup_dir, timestamp)
            
            # Backup media files if requested
            media_backup_path = None
            if options['backup_media']:
                media_backup_path = self.backup_media_files(backup_dir, timestamp)
            
            # Upload to S3 if requested
            if options['upload_s3']:
                self.upload_to_s3(
                    db_backup_path,
                    media_backup_path,
                    options['s3_bucket']
                )
            
            # Clean up old backups
            self.cleanup_old_backups(backup_dir, options['keep_local'])
            
            # Send notification
            if options['notification_email']:
                self.send_backup_notification(
                    options['notification_email'],
                    db_backup_path,
                    media_backup_path
                )
            
            self.stdout.write(
                self.style.SUCCESS('Backup completed successfully')
            )
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
            raise CommandError(f"Backup failed: {str(e)}")

    def setup_logging(self):
        """Configure logging for the backup process."""
        log_dir = os.path.join(settings.BASE_DIR, 'logs', 'backups')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(
            log_dir,
            f'backup_{timezone.now().strftime("%Y%m%d")}.log'
        )
        
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )

    def backup_database(self, backup_dir, timestamp):
        """
        Create database backup based on database engine.
        """
        db_settings = settings.DATABASES['default']
        engine = db_settings['ENGINE']
        
        if 'postgresql' in engine:
            return self.backup_postgresql(db_settings, backup_dir, timestamp)
        elif 'mysql' in engine:
            return self.backup_mysql(db_settings, backup_dir, timestamp)
        elif 'sqlite3' in engine:
            return self.backup_sqlite(db_settings, backup_dir, timestamp)
        else:
            raise CommandError(f"Unsupported database engine: {engine}")

    def backup_postgresql(self, db_settings, backup_dir, timestamp):
        """
        Create PostgreSQL database backup.
        """
        backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.sql.gz')
        
        try:
            # Construct pg_dump command
            command = [
                'pg_dump',
                '--dbname=postgresql://{user}:{password}@{host}:{port}/{name}'.format(
                    user=db_settings['USER'],
                    password=db_settings['PASSWORD'],
                    host=db_settings['HOST'],
                    port=db_settings['PORT'],
                    name=db_settings['NAME']
                )
            ]
            
            # Execute backup command
            with gzip.open(backup_file, 'wb') as f:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    raise CommandError(f"pg_dump failed: {stderr.decode()}")
                
                f.write(stdout)
            
            logger.info(f"PostgreSQL backup created: {backup_file}")
            return backup_file
            
        except Exception as e:
            logger.error(f"PostgreSQL backup failed: {str(e)}")
            raise

    def backup_mysql(self, db_settings, backup_dir, timestamp):
        """
        Create MySQL database backup.
        """
        backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.sql.gz')
        
        try:
            # Construct mysqldump command
            command = [
                'mysqldump',
                f"--user={db_settings['USER']}",
                f"--password={db_settings['PASSWORD']}",
                f"--host={db_settings['HOST']}",
                f"--port={db_settings['PORT']}",
                db_settings['NAME']
            ]
            
            # Execute backup command
            with gzip.open(backup_file, 'wb') as f:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                stdout, stderr = process.communicate()
                
                if process.returncode != 0:
                    raise CommandError(f"mysqldump failed: {stderr.decode()}")
                
                f.write(stdout)
            
            logger.info(f"MySQL backup created: {backup_file}")
            return backup_file
            
        except Exception as e:
            logger.error(f"MySQL backup failed: {str(e)}")
            raise

    def backup_sqlite(self, db_settings, backup_dir, timestamp):
        """
        Create SQLite database backup.
        """
        backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.sqlite.gz')
        
        try:
            # Copy and compress the SQLite file
            with open(db_settings['NAME'], 'rb') as src:
                with gzip.open(backup_file, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
            
            logger.info(f"SQLite backup created: {backup_file}")
            return backup_file
            
        except Exception as e:
            logger.error(f"SQLite backup failed: {str(e)}")
            raise

    def backup_media_files(self, backup_dir, timestamp):
        """
        Create backup of media files.
        """
        media_backup_file = os.path.join(backup_dir, f'media_backup_{timestamp}.tar.gz')
        
        try:
            # Create tar archive of media directory
            media_dir = settings.MEDIA_ROOT
            with tarfile.open(media_backup_file, 'w:gz') as tar:
                tar.add(media_dir, arcname=os.path.basename(media_dir))
            
            logger.info(f"Media files backup created: {media_backup_file}")
            return media_backup_file
            
        except Exception as e:
            logger.error(f"Media files backup failed: {str(e)}")
            raise

    def upload_to_s3(self, db_backup_path, media_backup_path, bucket_name):
        """
        Upload backup files to S3.
        """
        try:
            s3_client = boto3.client('s3')
            
            # Upload database backup
            if db_backup_path:
                s3_key = f"backups/db/{os.path.basename(db_backup_path)}"
                s3_client.upload_file(db_backup_path, bucket_name, s3_key)
                logger.info(f"Database backup uploaded to S3: {s3_key}")
            
            # Upload media backup
            if media_backup_path:
                s3_key = f"backups/media/{os.path.basename(media_backup_path)}"
                s3_client.upload_file(media_backup_path, bucket_name, s3_key)
                logger.info(f"Media backup uploaded to S3: {s3_key}")
            
        except Exception as e:
            logger.error(f"S3 upload failed: {str(e)}")
            raise

    def cleanup_old_backups(self, backup_dir, keep_days):
        """
        Remove old backup files.
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=keep_days)
            
            for filename in os.listdir(backup_dir):
                filepath = os.path.join(backup_dir, filename)
                
                # Skip if not a file
                if not os.path.isfile(filepath):
                    continue
                
                # Get file modification time
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_time < cutoff_date:
                    os.remove(filepath)
                    logger.info(f"Removed old backup: {filepath}")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
            raise

    def send_backup_notification(self, email, db_backup_path, media_backup_path):
        """
        Send email notification about backup status.
        """
        from django.core.mail import send_mail
        
        try:
            # Prepare notification message
            message = "Backup Status Report\n\n"
            
            if db_backup_path:
                message += f"Database Backup: {os.path.basename(db_backup_path)}\n"
                message += f"Size: {self.get_file_size(db_backup_path)}\n\n"
            
            if media_backup_path:
                message += f"Media Backup: {os.path.basename(media_backup_path)}\n"
                message += f"Size: {self.get_file_size(media_backup_path)}\n\n"
            
            message += f"Timestamp: {timezone.now()}\n"
            
            # Send email
            send_mail(
                subject='Backup Status Report',
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False
            )
            
            logger.info(f"Backup notification sent to {email}")
            
        except Exception as e:
            logger.error(f"Failed to send backup notification: {str(e)}")

    def get_file_size(self, filepath):
        """
        Get human-readable file size.
        """
        size = os.path.getsize(filepath)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"