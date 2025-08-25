"""
Dialog classes for ImxUp application.
Provides various dialog interfaces for user interaction.
"""

import os
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QCheckBox, QMessageBox, QGroupBox, QFormLayout,
    QPlainTextEdit, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor

from imxup_constants import (
    TEMPLATE_PLACEHOLDERS, SUCCESS_CREDENTIALS_SAVED,
    ERROR_NO_CREDENTIALS
)
from imxup_auth_manager import AuthenticationManager
from imxup_exceptions import AuthenticationError, ConfigurationError


class CredentialSetupDialog(QDialog):
    """Dialog for setting up authentication credentials"""
    
    credentials_saved = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth_manager = AuthenticationManager()
        self.setup_ui()
        self.load_existing_credentials()
    
    def setup_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Setup Credentials")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Authentication method selection
        method_group = QGroupBox("Authentication Method")
        method_layout = QVBoxLayout()
        
        self.username_radio = QCheckBox("Username/Password")
        self.api_key_radio = QCheckBox("API Key")
        
        self.username_radio.setChecked(True)
        self.username_radio.toggled.connect(self.on_method_changed)
        self.api_key_radio.toggled.connect(self.on_method_changed)
        
        method_layout.addWidget(self.username_radio)
        method_layout.addWidget(self.api_key_radio)
        method_group.setLayout(method_layout)
        layout.addWidget(method_group)
        
        # Username/Password fields
        self.cred_group = QGroupBox("Credentials")
        cred_layout = QFormLayout()
        
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        cred_layout.addRow("Username:", self.username_input)
        cred_layout.addRow("Password:", self.password_input)
        self.cred_group.setLayout(cred_layout)
        layout.addWidget(self.cred_group)
        
        # API Key field
        self.api_group = QGroupBox("API Key")
        api_layout = QFormLayout()
        
        self.api_key_input = QLineEdit()
        api_layout.addRow("API Key:", self.api_key_input)
        self.api_group.setLayout(api_layout)
        self.api_group.hide()
        layout.addWidget(self.api_group)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_credentials)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def on_method_changed(self):
        """Handle authentication method change"""
        if self.username_radio.isChecked():
            self.cred_group.show()
            self.api_group.hide()
            self.api_key_radio.setChecked(False)
        else:
            self.cred_group.hide()
            self.api_group.show()
            self.username_radio.setChecked(False)
    
    def load_existing_credentials(self):
        """Load existing credentials if available"""
        try:
            if self.auth_manager.load_credentials():
                if self.auth_manager.api_key:
                    self.api_key_radio.setChecked(True)
                    self.api_key_input.setText(self.auth_manager.api_key)
                elif self.auth_manager.username:
                    self.username_radio.setChecked(True)
                    self.username_input.setText(self.auth_manager.username)
                    self.password_input.setText(self.auth_manager.password)
        except Exception:
            pass
    
    def save_credentials(self):
        """Save the entered credentials"""
        try:
            if self.api_key_radio.isChecked():
                api_key = self.api_key_input.text().strip()
                if not api_key:
                    QMessageBox.warning(self, "Warning", "Please enter an API key")
                    return
                
                if self.auth_manager.save_credentials(api_key=api_key):
                    QMessageBox.information(self, "Success", SUCCESS_CREDENTIALS_SAVED)
                    self.credentials_saved.emit({
                        'type': 'api_key',
                        'api_key': api_key
                    })
                    self.accept()
                else:
                    QMessageBox.critical(self, "Error", "Failed to save credentials")
                    
            else:
                username = self.username_input.text().strip()
                password = self.password_input.text()
                
                if not username or not password:
                    QMessageBox.warning(self, "Warning", "Please enter both username and password")
                    return
                
                if self.auth_manager.save_credentials(username=username, password=password):
                    QMessageBox.information(self, "Success", SUCCESS_CREDENTIALS_SAVED)
                    self.credentials_saved.emit({
                        'type': 'username_password',
                        'username': username,
                        'password': password
                    })
                    self.accept()
                else:
                    QMessageBox.critical(self, "Error", "Failed to save credentials")
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save credentials: {e}")


class BBCodeViewerDialog(QDialog):
    """Dialog for viewing and copying BBCode"""
    
    def __init__(self, bbcode: str, gallery_name: str = "Gallery", parent=None):
        super().__init__(parent)
        self.bbcode = bbcode
        self.gallery_name = gallery_name
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize the UI"""
        self.setWindowTitle(f"BBCode - {self.gallery_name}")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # BBCode text area
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(self.bbcode)
        self.text_edit.setReadOnly(True)
        
        # Use monospace font
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(font)
        
        layout.addWidget(self.text_edit)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(copy_button)
        
        save_button = QPushButton("Save to File")
        save_button.clicked.connect(self.save_to_file)
        button_layout.addWidget(save_button)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def copy_to_clipboard(self):
        """Copy BBCode to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.bbcode)
        QMessageBox.information(self, "Success", "BBCode copied to clipboard!")
    
    def save_to_file(self):
        """Save BBCode to file"""
        from PyQt6.QtWidgets import QFileDialog
        
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save BBCode",
            f"{self.gallery_name}.txt",
            "Text Files (*.txt);;All Files (*.*)"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.bbcode)
                QMessageBox.information(self, "Success", f"BBCode saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {e}")


class HelpDialog(QDialog):
    """Help and documentation dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("ImxUp Help")
        self.setMinimumSize(700, 500)
        
        layout = QVBoxLayout()
        
        # Tab widget for different help sections
        tabs = QTabWidget()
        
        # Quick Start tab
        quick_start = QTextEdit()
        quick_start.setReadOnly(True)
        quick_start.setHtml(self.get_quick_start_html())
        tabs.addTab(quick_start, "Quick Start")
        
        # Features tab
        features = QTextEdit()
        features.setReadOnly(True)
        features.setHtml(self.get_features_html())
        tabs.addTab(features, "Features")
        
        # Templates tab
        templates = QTextEdit()
        templates.setReadOnly(True)
        templates.setHtml(self.get_templates_html())
        tabs.addTab(templates, "Templates")
        
        # Keyboard Shortcuts tab
        shortcuts = QTextEdit()
        shortcuts.setReadOnly(True)
        shortcuts.setHtml(self.get_shortcuts_html())
        tabs.addTab(shortcuts, "Shortcuts")
        
        layout.addWidget(tabs)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
        
        self.setLayout(layout)
    
    def get_quick_start_html(self) -> str:
        """Get Quick Start guide HTML"""
        return """
        <h2>Quick Start Guide</h2>
        <ol>
            <li><b>Setup Credentials:</b> Go to Settings → Credentials and enter your imx.to login details or API key</li>
            <li><b>Add Galleries:</b> Drag and drop folders containing images onto the main window</li>
            <li><b>Start Upload:</b> Click "Start All" or "Start" for individual galleries</li>
            <li><b>Monitor Progress:</b> Watch the progress bars and status updates</li>
            <li><b>Get Results:</b> Click "View BBCode" to get sharing codes when complete</li>
        </ol>
        
        <h3>Drag & Drop</h3>
        <p>Simply drag image folders from your file explorer and drop them onto the application window.
        Multiple folders can be dropped at once.</p>
        
        <h3>Templates</h3>
        <p>Use templates to customize BBCode output. Select a template before uploading or set a default
        in Settings.</p>
        """
    
    def get_features_html(self) -> str:
        """Get Features documentation HTML"""
        return """
        <h2>Features</h2>
        
        <h3>Upload Management</h3>
        <ul>
            <li>Parallel uploads for faster processing</li>
            <li>Automatic retry on failures</li>
            <li>Resume incomplete uploads</li>
            <li>Queue persistence between sessions</li>
        </ul>
        
        <h3>Gallery Options</h3>
        <ul>
            <li>Custom gallery names</li>
            <li>Public/Private visibility</li>
            <li>Multiple thumbnail sizes</li>
            <li>Various thumbnail formats (JPEG, PNG, WebP)</li>
        </ul>
        
        <h3>BBCode Templates</h3>
        <ul>
            <li>Customizable output templates</li>
            <li>Placeholder support for dynamic content</li>
            <li>Multiple templates for different forums</li>
        </ul>
        
        <h3>Auto-Archive</h3>
        <ul>
            <li>Automatic periodic uploads</li>
            <li>Watch folders for new content</li>
            <li>Scheduled processing</li>
        </ul>
        """
    
    def get_templates_html(self) -> str:
        """Get Templates documentation HTML"""
        placeholders_html = "<br>".join([f"<code>{p}</code> - {self.get_placeholder_description(p)}" 
                                         for p in TEMPLATE_PLACEHOLDERS])
        
        return f"""
        <h2>Templates</h2>
        
        <h3>Available Placeholders</h3>
        {placeholders_html}
        
        <h3>Example Template</h3>
        <pre>
[center][b]#folderName#[/b][/center]
[center]Images: #pictureCount# | Size: #folderSize#[/center]
[center]Resolution: #width#x#height#[/center]

#allImages#

[center][url=#galleryLink#]View Full Gallery[/url][/center]
        </pre>
        
        <h3>Creating Custom Templates</h3>
        <p>Go to Settings → Templates to create and manage your custom templates.
        Templates are saved in ~/.imxup/templates/ as .template files.</p>
        """
    
    def get_shortcuts_html(self) -> str:
        """Get Keyboard Shortcuts HTML"""
        return """
        <h2>Keyboard Shortcuts</h2>
        
        <table border="1" cellpadding="5">
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><b>Ctrl+O</b></td><td>Open folder browser</td></tr>
            <tr><td><b>Ctrl+S</b></td><td>Start all uploads</td></tr>
            <tr><td><b>Ctrl+P</b></td><td>Pause uploads</td></tr>
            <tr><td><b>Delete</b></td><td>Remove selected galleries</td></tr>
            <tr><td><b>Ctrl+A</b></td><td>Select all galleries</td></tr>
            <tr><td><b>Ctrl+C</b></td><td>Copy BBCode for selected</td></tr>
            <tr><td><b>F1</b></td><td>Open help</td></tr>
            <tr><td><b>F5</b></td><td>Refresh queue</td></tr>
            <tr><td><b>Ctrl+,</b></td><td>Open settings</td></tr>
            <tr><td><b>Ctrl+Q</b></td><td>Quit application</td></tr>
        </table>
        
        <h3>Mouse Actions</h3>
        <ul>
            <li><b>Double-click:</b> View gallery details</li>
            <li><b>Right-click:</b> Context menu with actions</li>
            <li><b>Drag & Drop:</b> Add folders to queue</li>
        </ul>
        """
    
    def get_placeholder_description(self, placeholder: str) -> str:
        """Get description for a template placeholder"""
        descriptions = {
            "#folderName#": "Name of the gallery/folder",
            "#pictureCount#": "Number of images in gallery",
            "#width#": "Average image width",
            "#height#": "Average image height",
            "#longest#": "Longest dimension",
            "#extension#": "Common file extension",
            "#folderSize#": "Total size of all images",
            "#galleryLink#": "URL to the gallery",
            "#allImages#": "All image BBCode tags"
        }
        return descriptions.get(placeholder, "Custom placeholder")


class PlaceholderHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for template placeholders"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.placeholder_format = QTextCharFormat()
        self.placeholder_format.setForeground(QColor(0, 128, 0))
        self.placeholder_format.setFontWeight(QFont.Weight.Bold)
    
    def highlightBlock(self, text: str):
        """Highlight placeholders in text"""
        for placeholder in TEMPLATE_PLACEHOLDERS:
            index = text.find(placeholder)
            while index >= 0:
                self.setFormat(index, len(placeholder), self.placeholder_format)
                index = text.find(placeholder, index + len(placeholder))