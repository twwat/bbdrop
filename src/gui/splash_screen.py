#!/usr/bin/env python3
"""
Splash screen with animated GIF and random status updates for imxup GUI
"""

import os
import random
import threading
import time
from PyQt6.QtWidgets import QSplashScreen, QApplication, QVBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QRectF
from PyQt6.QtGui import QPixmap, QFont, QPainter, QColor, QMovie, QPen, QPainterPath, QRegion


class SplashScreen(QSplashScreen):
    """Custom splash screen with animated GIF and status updates"""
    
    def __init__(self):
        # Create a base pixmap for the splash screen
        pixmap = QPixmap(540, 380)  # Increased height for logo
        pixmap.fill(QColor(29, 22, 22))  # Dark blue-gray background
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        
        # Load the imxup logo
        try:
            from imxup import get_project_root
            logo_path = os.path.join(get_project_root(), 'assets', 'imxup2.png')
            self.logo_pixmap = QPixmap(logo_path)
            if self.logo_pixmap.isNull():
                self.logo_pixmap = None
        except Exception:
            self.logo_pixmap = None
        self.init_action_words = [
            "initializing", "activating actuators", "establishing alibi", "connecting to skynet",
            "fabricating evidence", "concocting plan", "devising exit strategy", "improvising",
            "conspiring", "mobilizing", "arousing", "linking to mothership", "replicating replicants",
            "configuring", "populating microverse", "instantiating", "kicking", "Smashing",
            "rebooting", "stabilizing mood", "normalizing", "approximating", "recombinating",
            "extrapolating", "inseminating", "obliterating", "annihilating",
            "observifying", "calibrating", "accelerating", "optimizing", "flipping tables",
            "exorcising", "wiping back to front"]
        self.status_text = random.choice(self.init_action_words).title()
        self.progress_dots = ""
        
        # Random action words and objects
        self.action_words = [
            "initializing", "activating", "establishing", "launching", "constructing",
            "inventing", "fabricating", "concocting", "devising", "improvising",
            "actuating", "starting", "mobilizing", "arousing", "galvanizing",
            "configuring", "populating", "instantiating", "kicking", "muttering at",
            "rebooting", "stabilizing", "normalizing", "approximating", "recombinating",
            "deriving", "extrapolating", "inseminating", "obliterating", "annihilating",
            "observifying", "recalibrating", "accelerating", "optimizing", "intubating",
            "exorcising"
        ]
        
       
        # Get version info
        try:
            from imxup import __version__
            self.version = f"IMXup {__version__} "
        except:
            self.version = "v69"

        # Set rounded window shape
        self.setWindowShape()
    
    def setWindowShape(self):
        """Set the window to have rounded corners"""
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 75, 75)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
    
    def paintEvent(self, event):
        """Custom paint event to draw text and layout"""
        super().paintEvent(event)
        
        license_lines = [
            "Software distributed under the license is on an \"as is\"",
            "basis without warranties or conditions of any kind.",
        ]
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw rounded border with 2px thickness, 20px radius
        painter.setPen(QPen(QColor(207, 69, 2), 3))
        painter.drawRoundedRect(2, 2, self.width() - 3, self.height() - 3, 75, 75)
        
        # Draw logo at top if available
        y_offset = 16
        if self.logo_pixmap and not self.logo_pixmap.isNull():
            # Scale logo to fit nicely at top
            logo_height = 128
            logo_scaled = self.logo_pixmap.scaledToHeight(logo_height, Qt.TransformationMode.SmoothTransformation)
            logo_x = (self.width() - logo_scaled.width()) // 2
            painter.drawPixmap(logo_x, y_offset, logo_scaled)
            y_offset += logo_height
        
        # Draw version
        version_font = QFont("Courier", 13)
        painter.setFont(version_font)
        painter.setPen(QColor(253, 69, 32))
        version_rect = painter.fontMetrics().boundingRect(self.version)
        version_x = (self.width() - version_rect.width()) // 2
        painter.drawText(version_x, y_offset + 13, self.version)
        y_offset += 30
        
        copyright_text = "Copyright © 2025 twat"
        copyright_font = QFont("Courier", 11)
        painter.setFont(copyright_font)
        painter.setPen(QColor(123, 123, 123))
        copyright_rect = painter.fontMetrics().boundingRect(copyright_text)
        copyright_x = (self.width() - copyright_rect.width()) // 2
        painter.drawText(copyright_x, y_offset + 20, copyright_text)
        y_offset += 36
        
        apache_text = "Licensed under the Apache License, Version 2.0"
        apache_font = QFont("Courier", 10)
        painter.setFont(apache_font)
        painter.setPen(QColor(219, 219, 219))
        apache_rect = painter.fontMetrics().boundingRect(apache_text)
        apache_x = (self.width() - apache_rect.width()) // 2
        painter.drawText(apache_x, y_offset + 20, apache_text)
        y_offset += 58
        
        # Draw copyright and license info
        painter.setPen(QColor(212, 212, 212))
        license_font = QFont("Courier", 9)
        painter.setFont(license_font)
        
        y_pos = y_offset
        for line in license_lines:
            if line:
                line_rect = painter.fontMetrics().boundingRect(line)
                line_x = (self.width() - line_rect.width()) // 2
                painter.drawText(line_x, y_pos, line)
            y_pos += 15
        
        # Draw status text at bottom
        painter.setPen(QColor(210, 133, 133))
        status_font = QFont("Courier", 10, QFont.Weight.Bold)
        painter.setFont(status_font)
        
        status_rect = painter.fontMetrics().boundingRect(self.status_text)
        status_x = (self.width() - status_rect.width()) // 2
        painter.drawText(status_x, self.height() - 42, self.status_text)
        
        # Draw progress dots in fixed position (left-aligned within centered area)
        dots_font = QFont("Courier", 16)
        painter.setFont(dots_font)
        painter.setPen(QColor(169, 150, 150))
        
        # Create a fixed-width area for dots (centered, but dots are left-aligned within it)
        dots_area_width = 200
        dots_area_x = (self.width() - dots_area_width) // 2
        painter.drawText(dots_area_x, self.height() - 10, self.progress_dots)
        
        painter.end()
    
    
    def update_status(self, message):
        """Update the status message and repaint"""
        self.status_text = message
        self.repaint()
        QApplication.processEvents()  # Ensure UI updates immediately

    def set_status(self, text):
        """Set status text with random action word and add progress dot"""
        #self.random_timer.stop()
        action = random.choice(self.action_words).title()
        self.status_text = f"{action} {text}"
        self.progress_dots += "•"
        self.repaint()
        QApplication.processEvents()
    
    def finish_and_hide(self):
        """Clean shutdown of splash screen"""
        self.hide()
