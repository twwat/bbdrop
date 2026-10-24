"""When BBCode generation has to measure the folder, the JSON keeps the result."""
import json
import os
from unittest.mock import patch

import pytest
from PIL import Image

from src.utils.templates import save_gallery_artifacts

pytestmark = pytest.mark.unit


@patch('src.utils.templates.generate_bbcode_from_template', return_value="bbcode")
@patch('src.utils.templates.load_user_defaults', return_value={})
def test_measured_dimensions_are_written_to_json_stats(_defaults, _gen, tmp_path):
    for i in range(3):
        Image.new("RGB", (300, 200)).save(tmp_path / f"img{i}.jpg")
    results = {
        'gallery_id': 'abc12', 'gallery_name': 'measured', 'images': [],
        'successful_count': 3, 'failed_count': 0, 'total_size': 1000,
        'avg_width': 0, 'avg_height': 0, 'max_width': 0, 'max_height': 0,
        'min_width': 0, 'min_height': 0,
    }

    written = save_gallery_artifacts(
        folder_path=str(tmp_path), results=results,
        store_in_uploaded=True, store_in_central=False,
    )

    with open(written['uploaded']['json'], encoding='utf-8') as f:
        stats = json.load(f)['stats']
    assert (stats['avg_width'], stats['avg_height']) == (300, 200)
    assert (stats['max_width'], stats['max_height']) == (300, 200)
    assert (stats['min_width'], stats['min_height']) == (300, 200)
