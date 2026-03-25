"""Template loading, conditional processing, and gallery artifact generation."""

import os
import json
from datetime import datetime
from typing import Optional

from src.utils.logger import log
from src.utils.paths import (
    __version__,
    get_central_store_base_path,
    get_central_storage_path,
    load_user_defaults,
)


def get_template_path():
    """Get the template directory path (uses configured central store location)."""
    base_path = get_central_store_base_path()  # Use configured path, not hardcoded
    template_path = os.path.join(base_path, "templates")
    os.makedirs(template_path, exist_ok=True)
    return template_path

def get_default_template():
    """Get the default template content"""
    return "#folderName#\n#allImages#"

def load_templates():
    """Load all available templates from the template directory"""
    template_path = get_template_path()
    templates = {}

    # Add default template
    templates["default"] = get_default_template()

    # Add Extended Example template
    templates["Extended Example"] = """#folderName#
[hr][/hr]
[center][size=4][b][color=#11c153]#folderName#[/color][/b][/size]

[size=3][b][color="#888"]#pictureCount# IMAGES • #extension# • #width#x#height# • #folderSize# [/color] [/b][/font][/size]
[/center][hr][/hr]#allImages#
[if galleryLink][b]Gallery link[/b]: #galleryLink#[else][i][size=1]Sorry, no gallery link available.[/size][/i][/if]
ext1: [if ext1]#ext1#[else]no ext1 value set[/if]
ext2: [if ext2]#ext2#[else]no ext2 value set[/if]
ext3: [if ext3]#ext3#[else]no ext3 value set[/if]
ext4: [if ext4]#ext4#[else]no ext4 value set[/if]
custom1: [if custom1]#custom1#[else]no custom1 value set[/if]
custom2: [if custom2]#custom2#[else]no custom2 value set[/if]
custom3: [if custom3]#custom3#[else]no custom3 value set[/if]
custom4: [if custom4]#custom4#[else]no custom4 value set[/if]
[if hostLinks][b]Download links:[/b]
#hostLinks#[/if]"""

    # Load custom templates
    if os.path.exists(template_path):
        for filename in os.listdir(template_path):
            template_name = filename
            if template_name.startswith(".template"):
                template_name = template_name[10:]  # Remove ".template " prefix
            # Remove .txt extension if present
            if template_name.endswith('.template.txt'):
                template_name = template_name[:-13]
            if template_name.endswith('.txt'):
                template_name = template_name[:-4]
            if template_name:  # Skip empty names
                template_file = os.path.join(template_path, filename)
                try:
                    with open(template_file, 'r', encoding='utf-8') as f:
                        templates[template_name] = f.read()
                except Exception as e:
                    log(f"Could not load template '{template_name}': {e}", level="error", category="template")

    return templates

def _camel_to_snake(name):
    """Convert camelCase placeholder name to snake_case data key.

    Template placeholders use camelCase (e.g. downloadLinks, videoDetails)
    while data dicts use snake_case (e.g. download_links, video_details).
    """
    import re
    # Insert underscore before uppercase letters and lowercase the result
    return re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', name).lower()


def process_conditionals(template_content, data):
    """Process conditional logic in templates before placeholder replacement.

    Supports two syntax forms:
    1. [if placeholder]content[/if] - shows content if placeholder value is non-empty
    2. [if placeholder=value]content[else]alternative[/if] - shows content if placeholder equals value

    Features:
    - Multiple inline conditionals on the same line
    - Nested conditionals (processed inside-out)
    - Empty lines from removed conditionals are stripped
    - Placeholder names are matched as camelCase (template) or snake_case (data)
    """
    import re

    # Process conditionals iteratively until no more found
    max_iterations = 50  # Prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        # Look for innermost conditional pattern (no nested [if] tags inside)
        # This regex matches [if...] followed by content WITHOUT another [if, then [/if]
        if_pattern = r'\[if\s+(\w+)(=([^\]]+))?\]((?:(?!\[if).)*?)\[/if\]'
        match = re.search(if_pattern, template_content, re.DOTALL)

        if not match:
            # No more conditionals found
            break

        placeholder_name = match.group(1)
        expected_value = match.group(3)  # None if no = comparison
        conditional_block = match.group(4)  # Content between [if] and [/if]

        # Get the actual value from data -- try camelCase name first,
        # then fall back to snake_case conversion so that [if downloadLinks]
        # finds data['download_links'].
        actual_value = data.get(placeholder_name, '')
        if not actual_value:
            snake_key = _camel_to_snake(placeholder_name)
            if snake_key != placeholder_name:
                actual_value = data.get(snake_key, '')

        # Check for [else] clause (only at top level, not nested)
        else_pattern = r'^(.*?)\[else\](.*?)$'
        else_match = re.match(else_pattern, conditional_block, re.DOTALL)

        if else_match:
            true_content = else_match.group(1)
            false_content = else_match.group(2)
        else:
            true_content = conditional_block
            false_content = ''

        # Determine condition
        if expected_value is not None:
            # Equality check: [if placeholder=value]
            condition_met = (str(actual_value).strip() == expected_value.strip())
        else:
            # Existence check: [if placeholder]
            condition_met = bool(str(actual_value).strip())

        # Select content based on condition
        selected_content = true_content if condition_met else false_content

        # Replace the entire conditional block with selected content
        template_content = template_content[:match.start()] + selected_content + template_content[match.end():]

        iteration += 1

    # Clean up empty lines
    lines = template_content.split('\n')
    cleaned_lines = [line for line in lines if line.strip() or line == '']  # Keep intentional blank lines

    # Remove consecutive empty lines and leading/trailing empty lines
    result_lines = []
    prev_empty = False
    for line in cleaned_lines:
        is_empty = not line.strip()
        if is_empty:
            if not prev_empty and result_lines:  # Keep one empty line
                result_lines.append(line)
            prev_empty = True
        else:
            result_lines.append(line)
            prev_empty = False

    # Remove trailing empty lines
    while result_lines and not result_lines[-1].strip():
        result_lines.pop()

    return '\n'.join(result_lines)

def apply_template(template_content, data):
    """Apply a template with data replacement"""
    # Process conditional logic first (before placeholder replacement)
    result = process_conditionals(template_content, data)

    # Replace placeholders with actual data
    # hostLinks and allImages are expanded FIRST so that any main placeholders
    # embedded inside them (e.g. #folderSize# in a filehost bbcode_format)
    # get resolved in the second pass.
    composite_replacements = {
        '#hostLinks#': data.get('host_links', ''),
        '#allImages#': data.get('all_images', ''),
        '#cover#': data.get('cover', ''),
        '#videoDetails#': data.get('video_details', ''),
        '#screenshotSheet#': data.get('screenshot_sheet', ''),
        '#downloadLinks#': data.get('download_links', ''),
    }
    for placeholder, value in composite_replacements.items():
        result = result.replace(placeholder, str(value or ''))

    replacements = {
        '#folderName#': str(data.get('folder_name') or ''),
        '#width#': str(data.get('width', 0)),
        '#height#': str(data.get('height', 0)),
        '#longest#': str(data.get('longest', 0)),
        '#extension#': str(data.get('extension') or ''),
        '#pictureCount#': str(data.get('picture_count', 0)),
        '#folderSize#': str(data.get('folder_size') or ''),
        '#galleryLink#': str(data.get('gallery_link') or ''),
        '#custom1#': str(data.get('custom1') or ''),
        '#custom2#': str(data.get('custom2') or ''),
        '#custom3#': str(data.get('custom3') or ''),
        '#custom4#': str(data.get('custom4') or ''),
        '#ext1#': str(data.get('ext1') or ''),
        '#ext2#': str(data.get('ext2') or ''),
        '#ext3#': str(data.get('ext3') or ''),
        '#ext4#': str(data.get('ext4') or ''),
        '#filename#': str(data.get('filename', '')),
        '#duration#': str(data.get('duration', '')),
        '#resolution#': str(data.get('resolution', '')),
        '#fps#': str(data.get('fps', '')),
        '#bitrate#': str(data.get('bitrate', '')),
        '#videoCodec#': str(data.get('video_codec', '')),
        '#audioCodec#': str(data.get('audio_codec', '')),
        '#audioTracks#': str(data.get('audio_tracks', '')),
        '#filesize#': str(data.get('filesize', '')),
    }
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value or ''))

    return result

def generate_bbcode_from_template(template_name, data):
    """Generate bbcode content using a specific template"""
    templates = load_templates()

    if template_name not in templates:
        log(f"Template '{template_name}' not found, using default", level="warning", category="template")
        template_name = "default"

    template_content = templates[template_name]
    return apply_template(template_content, data)


def save_gallery_artifacts(
    folder_path: str,
    results: dict,
    template_name: str = "default",
    store_in_uploaded: Optional[bool] = None,
    store_in_central: Optional[bool] = None,
    custom_fields: Optional[dict] = None,
    cover_bbcode: str = "",
) -> dict:
    """Save BBCode and JSON artifacts for a completed gallery.

    Parameters:
    - folder_path: path to the source image folder
    - results: the results dict returned by upload_folder (must contain keys used below)
    - template_name: which template to use for full bbcode generation
    - store_in_uploaded/store_in_central: overrides for storage locations. When None, read defaults
    - custom_fields: optional dict with custom1-4 and ext1-4 values

    Returns: dict with paths written: { 'uploaded': {'bbcode': str, 'json': str}, 'central': {...}}
    """
    from src.storage.gallery_management import build_gallery_filenames

    # Determine storage preferences
    defaults = load_user_defaults()
    if store_in_uploaded is None:
        store_in_uploaded = defaults.get('store_in_uploaded', True)
    if store_in_central is None:
        store_in_central = defaults.get('store_in_central', True)

    gallery_id = results.get('gallery_id', '')
    gallery_name = results.get('gallery_name') or os.path.basename(folder_path)
    if not gallery_id or not gallery_name:
        return {}

    # Ensure .uploaded exists if needed
    uploaded_subdir = os.path.join(folder_path, ".uploaded")
    if store_in_uploaded:
        os.makedirs(uploaded_subdir, exist_ok=True)

    # Build filenames
    safe_gallery_name, json_filename, bbcode_filename = build_gallery_filenames(gallery_name, gallery_id)

    # Prepare template data from results for full bbcode
    total_size = results.get('total_size', 0)
    successful_images = results.get('successful_count', len(results.get('images', [])))
    avg_width = int(results.get('avg_width', 0) or 0)
    avg_height = int(results.get('avg_height', 0) or 0)

    # Fallback: Calculate from files if dimensions are missing
    if (avg_width == 0 or avg_height == 0) and os.path.isdir(folder_path):
        from src.utils.sampling_utils import calculate_folder_dimensions
        calc = calculate_folder_dimensions(folder_path)
        if calc:
            avg_width = int(calc.get('avg_width', 0))
            avg_height = int(calc.get('avg_height', 0))

    extension = "JPG"
    try:
        # Best-effort derive the most common extension from images if present
        exts = []
        for img in results.get('images', []):
            orig = img.get('original_filename') or ''
            if orig:
                _, ext = os.path.splitext(orig)
                if ext:
                    exts.append(ext.upper().lstrip('.'))
        if exts:
            extension = max(set(exts), key=exts.count)
    except Exception:
        pass

    # All-images bbcode (space-separated)
    # Generate per-image BBCode from image_url + thumb_url if not already present
    bbcode_parts = []
    for img in results.get('images', []):
        bb = img.get('bbcode')
        if not bb:
            iu = img.get('image_url', '')
            tu = img.get('thumb_url', '')
            if iu and tu:
                bb = f"[url={iu}][img]{tu}[/img][/url]"
            elif iu:
                bb = f"[url={iu}]{iu}[/url]"
        if bb:
            bbcode_parts.append(bb)
    all_images_bbcode = "  ".join(bbcode_parts)

    # Get file host data from database
    queue_store = None
    try:
        from src.storage.database import QueueStore
        queue_store = QueueStore()
    except Exception as e:
        log(f"Failed to open queue store for artifacts: {e}", level="warning", category="artifact")

    # Get file host download links for BBCode template
    host_links = ''
    if queue_store:
        try:
            from src.utils.template_utils import get_file_host_links_for_template
            host_links = get_file_host_links_for_template(queue_store, folder_path)
        except Exception as e:
            log(f"Failed to get file host links: {e}", level="warning", category="template")

    # Build file_hosts array for JSON artifact
    file_hosts_data = []
    if queue_store:
        try:
            fh_uploads = queue_store.get_file_host_uploads(folder_path)
            for u in fh_uploads:
                if u['status'] == 'completed' and u.get('download_url'):
                    file_hosts_data.append({
                        'host': u['host_name'],
                        'download_url': u['download_url'],
                        'file_id': u.get('file_id', ''),
                        'file_name': u.get('file_name', ''),
                        'md5_hash': u.get('md5_hash', ''),
                        'file_size': u.get('file_size', 0),
                        'deduped': u.get('deduped', False),
                        'part': u.get('part_number', 0) + 1,
                    })
        except Exception as e:
            log(f"Failed to build file_hosts artifact data: {e}", level="warning", category="artifact")

    # Get cover info from results if available (cover_result is a list of per-cover dicts)
    cover_results = results.get('cover_result', []) or []
    c_url = next((r.get('image_url', '') for r in cover_results if r.get('status') == 'success'), '')
    c_thumb = next((r.get('thumb_url', '') for r in cover_results if r.get('status') == 'success'), '')
    if not cover_bbcode:
        cover_bbcode = "\n".join(
            r['bbcode'] for r in cover_results
            if r.get('status') == 'success' and r.get('bbcode')
        )

    template_data = {
        'folder_name': gallery_name,
        'width': avg_width,
        'height': avg_height,
        'longest': max(avg_width, avg_height),
        'extension': extension,
        'picture_count': successful_images,
        'folder_size': f"{total_size / (1024*1024):.1f} MB",
        'gallery_link': results.get('gallery_url', ''),
        'all_images': all_images_bbcode,
        'host_links': host_links,
        'cover': cover_bbcode,
        'cover_url': c_url,
        'cover_thumb_url': c_thumb,
        'custom1': (custom_fields or {}).get('custom1', ''),
        'custom2': (custom_fields or {}).get('custom2', ''),
        'custom3': (custom_fields or {}).get('custom3', ''),
        'custom4': (custom_fields or {}).get('custom4', ''),
        'ext1': (custom_fields or {}).get('ext1', ''),
        'ext2': (custom_fields or {}).get('ext2', ''),
        'ext3': (custom_fields or {}).get('ext3', ''),
        'ext4': (custom_fields or {}).get('ext4', '')
    }
    bbcode_content = generate_bbcode_from_template(template_name, template_data)

    # Compose JSON payload (align with CLI structure)
    json_payload = {
        'meta': {
            'gallery_name': gallery_name,
            'gallery_id': gallery_id,
            'gallery_url': results.get('gallery_url', ''),
            'status': 'completed',
            'started_at': results.get('started_at') or None,
            'finished_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uploader_version': __version__,
        },
        'settings': {
            'thumbnail_size': results.get('thumbnail_size'),
            'thumbnail_format': results.get('thumbnail_format'),
            'template_name': template_name,
            'parallel_batch_size': results.get('parallel_batch_size'),
        },
        'stats': {
            'total_images': results.get('total_images') or (successful_images + results.get('failed_count', 0)),
            'successful_count': successful_images,
            'failed_count': results.get('failed_count', 0),
            'upload_time': results.get('upload_time', 0),
            'total_size': total_size,
            'uploaded_size': results.get('uploaded_size', 0),
            'avg_width': results.get('avg_width', 0),
            'avg_height': results.get('avg_height', 0),
            'max_width': results.get('max_width', 0),
            'max_height': results.get('max_height', 0),
            'min_width': results.get('min_width', 0),
            'min_height': results.get('min_height', 0),
            'transfer_speed_mb_s': (results.get('transfer_speed', 0) / (1024*1024)) if results.get('transfer_speed', 0) else 0,
        },
        'images': results.get('images', []),
        'cover_result': cover_results,
        'file_hosts': file_hosts_data,
        'failures': [
            {
                'filename': fname,
                'failed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'reason': reason,
            }
            for fname, reason in results.get('failed_details', [])
        ],
        'bbcode_full': bbcode_content,
    }

    written_paths = {}
    # Save BBCode and JSON to .uploaded
    if store_in_uploaded:
        with open(os.path.join(uploaded_subdir, bbcode_filename), 'w', encoding='utf-8') as f:
            f.write(bbcode_content)
        with open(os.path.join(uploaded_subdir, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        written_paths.setdefault('uploaded', {})['bbcode'] = os.path.join(uploaded_subdir, bbcode_filename)
        written_paths.setdefault('uploaded', {})['json'] = os.path.join(uploaded_subdir, json_filename)

    # Save to central location as well
    if store_in_central:
        central_path = get_central_storage_path()
        os.makedirs(central_path, exist_ok=True)
        with open(os.path.join(central_path, bbcode_filename), 'w', encoding='utf-8') as f:
            f.write(bbcode_content)
        with open(os.path.join(central_path, json_filename), 'w', encoding='utf-8') as jf:
            json.dump(json_payload, jf, ensure_ascii=False, indent=2)
        written_paths.setdefault('central', {})['bbcode'] = os.path.join(central_path, bbcode_filename)
        written_paths.setdefault('central', {})['json'] = os.path.join(central_path, json_filename)

    return written_paths
