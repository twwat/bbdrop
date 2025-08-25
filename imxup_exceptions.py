"""
Custom exception hierarchy for ImxUp application.
Provides specific exceptions for different error scenarios.
"""

class ImxUpException(Exception):
    """Base exception for all ImxUp errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(ImxUpException):
    """Raised when authentication fails"""
    pass


class CredentialError(AuthenticationError):
    """Raised when credentials are missing or invalid"""
    pass


class SessionError(AuthenticationError):
    """Raised when session management fails"""
    pass


class APIKeyError(AuthenticationError):
    """Raised when API key is invalid or missing"""
    pass


class UploadError(ImxUpException):
    """Base class for upload-related errors"""
    pass


class ImageUploadError(UploadError):
    """Raised when an image upload fails"""
    def __init__(self, message: str, image_path: str = None, gallery_id: str = None, details: dict = None):
        super().__init__(message, details)
        self.image_path = image_path
        self.gallery_id = gallery_id


class GalleryCreationError(UploadError):
    """Raised when gallery creation fails"""
    def __init__(self, message: str, gallery_name: str = None, details: dict = None):
        super().__init__(message, details)
        self.gallery_name = gallery_name


class GalleryRenameError(UploadError):
    """Raised when gallery rename fails"""
    def __init__(self, message: str, gallery_id: str = None, new_name: str = None, details: dict = None):
        super().__init__(message, details)
        self.gallery_id = gallery_id
        self.new_name = new_name


class NetworkError(ImxUpException):
    """Raised for network-related issues"""
    pass


class ConnectionError(NetworkError):
    """Raised when connection to server fails"""
    pass


class TimeoutError(NetworkError):
    """Raised when a network operation times out"""
    pass


class RateLimitError(NetworkError):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str, retry_after: int = None, details: dict = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class ValidationError(ImxUpException):
    """Raised when input validation fails"""
    pass


class FileValidationError(ValidationError):
    """Raised when file validation fails"""
    def __init__(self, message: str, file_path: str = None, details: dict = None):
        super().__init__(message, details)
        self.file_path = file_path


class ImageValidationError(FileValidationError):
    """Raised when image validation fails"""
    pass


class ConfigurationError(ImxUpException):
    """Raised for configuration-related issues"""
    pass


class SettingsError(ConfigurationError):
    """Raised when settings are invalid or missing"""
    pass


class TemplateError(ConfigurationError):
    """Raised when template processing fails"""
    def __init__(self, message: str, template_name: str = None, details: dict = None):
        super().__init__(message, details)
        self.template_name = template_name


class StorageError(ImxUpException):
    """Raised for storage-related issues"""
    pass


class DatabaseError(StorageError):
    """Raised when database operations fail"""
    pass


class QueueError(StorageError):
    """Raised when queue operations fail"""
    pass


class SecurityError(ImxUpException):
    """Raised for security-related issues"""
    pass


class EncryptionError(SecurityError):
    """Raised when encryption/decryption fails"""
    pass


class PermissionError(SecurityError):
    """Raised when permission is denied"""
    pass


class IntegrityError(SecurityError):
    """Raised when data integrity check fails"""
    pass


class WorkerError(ImxUpException):
    """Raised for worker thread issues"""
    pass


class ThreadPoolError(WorkerError):
    """Raised when thread pool operations fail"""
    pass


class TaskError(WorkerError):
    """Raised when a background task fails"""
    def __init__(self, message: str, task_name: str = None, details: dict = None):
        super().__init__(message, details)
        self.task_name = task_name


class GUIError(ImxUpException):
    """Raised for GUI-related issues"""
    pass


class WidgetError(GUIError):
    """Raised when widget operations fail"""
    pass


class DialogError(GUIError):
    """Raised when dialog operations fail"""
    pass


class SystemError(ImxUpException):
    """Raised for system-level issues"""
    pass


class ResourceError(SystemError):
    """Raised when system resources are exhausted"""
    pass


class MemoryError(ResourceError):
    """Raised when memory limits are exceeded"""
    pass


class DiskSpaceError(ResourceError):
    """Raised when disk space is insufficient"""
    pass