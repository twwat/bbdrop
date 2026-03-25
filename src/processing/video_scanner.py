"""Video metadata extraction using OpenCV and pymediainfo."""
import os
from typing import Optional

import cv2
from pymediainfo import MediaInfo

from src.utils.logger import log


class VideoScanner:
    """Extracts video metadata for queue scanning and template placeholders."""

    def extract_cv2_metadata(self, path: str) -> Optional[dict]:
        """Extract basic video properties via OpenCV."""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            log(f"VideoScanner: cannot open {path}")
            cap.release()
            return None
        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0.0
            return {
                'width': width,
                'height': height,
                'fps': fps,
                'frame_count': frame_count,
                'duration': duration,
            }
        except Exception as e:
            log(f"VideoScanner: failed to read metadata from {path}: {e}")
            return None
        finally:
            cap.release()

    def extract_mediainfo(self, path: str) -> dict:
        """Extract detailed stream info via pymediainfo."""
        mi = MediaInfo.parse(path)
        video_streams = []
        audio_streams = []

        for track in mi.tracks:
            if track.track_type == 'Video':
                video_streams.append({
                    'format': getattr(track, 'format', None),
                    'codec_id': getattr(track, 'codec_id', None),
                    'width': getattr(track, 'width', None),
                    'height': getattr(track, 'height', None),
                    'frame_rate': getattr(track, 'frame_rate', None),
                    'bit_rate': getattr(track, 'bit_rate', None),
                    'color_space': getattr(track, 'color_space', None),
                    'chroma_subsampling': getattr(track, 'chroma_subsampling', None),
                })
            elif track.track_type == 'Audio':
                audio_streams.append({
                    'format': getattr(track, 'format', None),
                    'channels': getattr(track, 'channels', None),
                    'bit_depth': getattr(track, 'bit_depth', None),
                    'sampling_rate': getattr(track, 'sampling_rate', None),
                    'bit_rate': getattr(track, 'bit_rate', None),
                })

        return {'video': video_streams, 'audio': audio_streams}

    def scan(self, path: str) -> Optional[dict]:
        """Full scan: combine OpenCV + pymediainfo + file size."""
        try:
            cv2_meta = self.extract_cv2_metadata(path)
            if cv2_meta is None:
                return None

            streams = self.extract_mediainfo(path)
            filesize = os.path.getsize(path)

            return {
                'width': cv2_meta['width'],
                'height': cv2_meta['height'],
                'fps': cv2_meta['fps'],
                'frame_count': cv2_meta['frame_count'],
                'duration': cv2_meta['duration'],
                'filesize': filesize,
                'video_streams': streams['video'],
                'audio_streams': streams['audio'],
            }
        except Exception as e:
            log(f"VideoScanner: scan failed for {path}: {e}")
            return None
