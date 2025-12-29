"""
Script to fix mock issues in test_engine.py

The problem: side_effect lists get exhausted during retries, causing 'Mock' object errors.
The solution: Use callable functions that always return valid data.
"""

import os

def create_mock_upload_function():
    """
    Create a function that always returns valid upload response.
    This prevents exhausting side_effect lists during retries.
    """
    upload_count = [0]  # Use list to allow mutation in closure

    def mock_upload(image_path, gallery_id=None, create_gallery=False, **kwargs):
        """Mock upload function that always returns success."""
        upload_count[0] += 1

        # For first upload (create gallery)
        if create_gallery or gallery_id is None:
            return {
                'status': 'success',
                'data': {
                    'gallery_id': 'gal123',
                    'image_url': f'http://imx.to/i/abc/img{upload_count[0]}.jpg',
                    'thumbnail_url': f'http://imx.to/i/abc/thumb{upload_count[0]}.jpg',
                    'delete_url': 'http://imx.to/delete/abc123'
                }
            }

        # For subsequent uploads to existing gallery
        return {
            'status': 'success',
            'data': {
                'gallery_id': gallery_id or 'gal123',
                'image_url': f'http://imx.to/i/abc/img{upload_count[0]}.jpg',
                'thumbnail_url': f'http://imx.to/i/abc/thumb{upload_count[0]}.jpg'
            }
        }

    return mock_upload


# Example of fixed test
FIXED_TEST_EXAMPLE = '''
def test_engine_creates_new_gallery_with_first_image(self, temp_image_folder):
    """Test engine creates new gallery by uploading first image."""
    mock_uploader = Mock()

    # OLD (BROKEN - exhausts after 3 calls):
    # mock_uploader.upload_image.side_effect = [
    #     {'status': 'success', 'data': {...}},
    #     {'status': 'success', 'data': {...}},
    #     {'status': 'success', 'data': {...}}
    # ]

    # NEW (FIXED - works for infinite calls including retries):
    def mock_upload(image_path, gallery_id=None, create_gallery=False, **kwargs):
        return {
            'status': 'success',
            'data': {
                'gallery_id': gallery_id or 'gal123',
                'image_url': f'http://imx.to/i/abc/{os.path.basename(image_path)}',
                'thumbnail_url': f'http://imx.to/i/abc/thumb_{os.path.basename(image_path)}'
            }
        }

    mock_uploader.upload_image.side_effect = mock_upload

    engine = UploadEngine(mock_uploader)
    result = engine.run(
        folder_path=temp_image_folder,
        gallery_name="Test Gallery",
        thumbnail_size=3,
        thumbnail_format=2,
        max_retries=3,
        parallel_batch_size=2,
        template_name="default"
    )

    assert result['gallery_id'] == 'gal123'
    assert result['successful_count'] == 3
'''

print("Mock fix strategy:")
print("=" * 60)
print("PROBLEM: side_effect lists exhaust during retries")
print("SOLUTION: Use callable functions that always return valid data")
print("=" * 60)
print(FIXED_TEST_EXAMPLE)
