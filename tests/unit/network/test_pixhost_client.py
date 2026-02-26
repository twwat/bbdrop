import os
import json
import pytest
from unittest.mock import patch, MagicMock

from src.network.pixhost_client import PixhostClient

@pytest.fixture
def pixhost_client():
    with patch('src.core.image_host_config.get_image_host_config_manager') as mock_mgr:
        yield PixhostClient()

def test_pixhost_create_gallery(pixhost_client):
    with patch('pycurl.Curl') as mock_curl_class:
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        
        mock_curl.getinfo.return_value = 200
        
        def mock_perform():
            # Find WRITEDATA buffer
            for call in mock_curl.setopt.call_args_list:
                if call[0][0] == 10001:  # pycurl.WRITEDATA
                    buffer = call[0][1]
                    buffer.write(json.dumps({
                        'gallery_hash': 'hash123',
                        'gallery_upload_hash': 'upload_hash123'
                    }).encode('utf-8'))
                    break
        mock_curl.perform.side_effect = mock_perform
        
        success_hash = pixhost_client.create_gallery('Test Gallery')
        
        assert success_hash == 'hash123'
        assert pixhost_client._gallery_hash == 'hash123'
        assert pixhost_client._gallery_upload_hash == 'upload_hash123'

def test_pixhost_upload_image_success(pixhost_client, tmpdir):
    img_path = os.path.join(tmpdir, "test.jpg")
    with open(img_path, "wb") as f:
        f.write(b"fake_image_data")
        
    with patch('pycurl.Curl') as mock_curl_class:
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        
        mock_curl.getinfo.return_value = 200
        
        def mock_perform():
            for call in mock_curl.setopt.call_args_list:
                if call[0][0] == 10001:  # pycurl.WRITEDATA
                    buffer = call[0][1]
                    buffer.write(json.dumps({
                        'name': 'test.jpg',
                        'show_url': 'https://pixhost.to/show/test/123_test.jpg',
                        'th_url': 'https://t1.pixhost.to/thumbs/test/123_test.jpg'
                    }).encode('utf-8'))
                    break
        mock_curl.perform.side_effect = mock_perform
        
        result = pixhost_client.upload_image(img_path)
        
        assert result['status'] == 'success'
        assert result['data']['image_url'] == 'https://pixhost.to/show/test/123_test.jpg'
        assert result['data']['thumb_url'] == 'https://t1.pixhost.to/thumbs/test/123_test.jpg'
        assert '[URL=' in result['data']['bbcode']

def test_pixhost_upload_image_fake_200(pixhost_client, tmpdir):
    img_path = os.path.join(tmpdir, "test.jpg")
    with open(img_path, "wb") as f:
        f.write(b"fake_image_data")
        
    with patch('pycurl.Curl') as mock_curl_class:
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        
        mock_curl.getinfo.return_value = 200
        
        def mock_perform():
            for call in reversed(mock_curl.setopt.call_args_list):
                if call[0][0] == 10001:  # pycurl.WRITEDATA
                    buffer = call[0][1]
                    buffer.write(json.dumps({
                        'name': 'test.jpg',
                        'show_url': 'https://pixhost.to/show/test/',
                        'th_url': 'https://t1.pixhost.to/thumbs/test/'
                    }).encode('utf-8'))
                    break
        mock_curl.perform.side_effect = mock_perform
        
        with patch('src.network.pixhost_client.get_image_host_setting', return_value='retry_image'):
            with pytest.raises(Exception, match="Pixhost returned fake 200 response"):
                pixhost_client.upload_image(img_path)

        with patch('src.network.pixhost_client.get_image_host_setting', return_value='retry_gallery'):
            with pytest.raises(Exception, match="Gallery corrupted due to Pixhost internal error on test.jpg"):
                pixhost_client.upload_image(img_path)
