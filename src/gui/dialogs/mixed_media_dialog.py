"""Dialog for handling folders with mixed image and video content."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox,
    QPushButton, QHBoxLayout,
)


class MixedMediaDialog(QDialog):
    """Prompt user when a folder contains both images and videos."""

    INCLUDE_IMAGES = "include"
    EXCLUDE_IMAGES = "exclude"

    def __init__(self, folder_name: str, image_count: int, video_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mixed Content Detected")
        self.result_choice = self.EXCLUDE_IMAGES

        layout = QVBoxLayout(self)

        info = QLabel(
            f'<b>{folder_name}</b> contains {image_count} image(s) '
            f'and {video_count} video(s).'
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        question = QLabel("Include images with the video?")
        layout.addWidget(question)

        self.remember_checkbox = QCheckBox("Remember my choice")
        layout.addWidget(self.remember_checkbox)

        button_layout = QHBoxLayout()
        yes_btn = QPushButton("Yes, include images")
        no_btn = QPushButton("No, videos only")
        yes_btn.clicked.connect(self._accept_include)
        no_btn.clicked.connect(self._accept_exclude)
        button_layout.addWidget(yes_btn)
        button_layout.addWidget(no_btn)
        layout.addLayout(button_layout)

    def _accept_include(self):
        self.result_choice = self.INCLUDE_IMAGES
        self.accept()

    def _accept_exclude(self):
        self.result_choice = self.EXCLUDE_IMAGES
        self.accept()

    @property
    def should_remember(self) -> bool:
        return self.remember_checkbox.isChecked()
