import boto3
import pickle
import logging
from io import BytesIO
from typing import Any, Dict, Optional
from botocore.exceptions import ClientError
from config import settings

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self):
        self.client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket = settings.S3_BUCKET_NAME

    def _get_user_path(self, user_id: str, file_type: str) -> str:
        """Generate S3 path for user files."""
        return f"users/{user_id}/{file_type}.pkl"

    async def save_data(self, user_id: str, data: Any, file_type: str) -> None:
        """Save pickled data to user's S3 location."""
        try:
            logger.info(f"Attempting to save {file_type} for user {user_id}")
            
            # Create BytesIO object and pickle the data
            buffer = BytesIO()
            pickle.dump(data, buffer)
            buffer.seek(0)
            
            # Generate S3 key
            key = self._get_user_path(user_id, file_type)
            
            # Upload to S3
            self.client.upload_fileobj(buffer, self.bucket, key)
            logger.info(f"Successfully saved {file_type} for user {user_id}")
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchBucket':
                logger.error(f"Bucket {self.bucket} does not exist")
                raise Exception(f"S3 bucket {self.bucket} does not exist")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to S3 bucket {self.bucket}")
                raise Exception("Access denied to S3 bucket")
            else:
                logger.error(f"AWS Error saving {file_type} for user {user_id}: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Error saving {file_type} to S3 for user {user_id}: {str(e)}")
            raise

    async def load_data(self, user_id: str, file_type: str) -> Optional[Any]:
        """Load pickled data from user's S3 location."""
        try:
            logger.info(f"Attempting to load {file_type} for user {user_id}")
            
            key = self._get_user_path(user_id, file_type)
            buffer = BytesIO()
            
            try:
                self.client.download_fileobj(self.bucket, key, buffer)
                buffer.seek(0)
                data = pickle.load(buffer)
                logger.info(f"Successfully loaded {file_type} for user {user_id}")
                return data
            except ClientError as e:
                error_code = e.response['Error'].get('Code')
                if error_code in ['NoSuchKey', '404']:
                    # First time user or file doesn't exist yet - this is normal
                    logger.info(f"No existing {file_type} found for user {user_id} - first time initialization")
                    return None
                # For other AWS errors, raise the exception
                raise
                
        except Exception as e:
            if 'HeadObject operation: Not Found' in str(e):
                logger.info(f"No existing {file_type} found for user {user_id} - first time initialization")
                return None
            logger.error(f"Error loading {file_type} from S3 for user {user_id}: {str(e)}")
            raise

    async def delete_user_data(self, user_id: str) -> None:
        """Delete all data for a user."""
        try:
            logger.info(f"Attempting to delete all data for user {user_id}")
            
            # List all objects with user prefix
            prefix = f"users/{user_id}/"
            paginator = self.client.get_paginator('list_objects_v2')
            objects_deleted = 0
            
            # Paginate through all objects
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                if 'Contents' in page:
                    objects = [{'Key': obj['Key']} for obj in page['Contents']]
                    objects_deleted += len(objects)
                                        
                    # Delete objects
                    self.client.delete_objects(
                        Bucket=self.bucket,
                        Delete={'Objects': objects}
                    )
            
            if objects_deleted > 0:
                logger.info(f"Successfully deleted {objects_deleted} objects for user {user_id}")
            else:
                logger.info(f"No data found to delete for user {user_id}")
                
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchBucket':
                logger.error(f"Bucket {self.bucket} does not exist")
                raise Exception(f"S3 bucket {self.bucket} does not exist")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to S3 bucket {self.bucket}")
                raise Exception("Access denied to S3 bucket")
            else:
                logger.error(f"AWS Error deleting data for user {user_id}: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Error deleting data for user {user_id}: {str(e)}")
            raise

    async def check_user_data_exists(self, user_id: str) -> Dict[str, bool]:
        """Check which data files exist for a user."""
        try:
            prefix = f"users/{user_id}/"
            response = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix
            )
            
            existing_files = [obj['Key'] for obj in response.get('Contents', [])]
            
            return {
                'posts': f"{prefix}posts.pkl" in existing_files,
                'chunked_posts': f"{prefix}chunked_posts.pkl" in existing_files
            }
            
        except ClientError as e:
            logger.error(f"AWS Error checking user data: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error checking user data: {str(e)}")
            raise