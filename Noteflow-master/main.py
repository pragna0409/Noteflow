import sys
import json
import os
import pickle
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,  
                            QTextEdit, QPushButton, QLabel, QListWidget, QListWidgetItem, 
                            QFrame, QProgressBar, QFileDialog, QLineEdit, 
                            QDateTimeEdit, QMenu, QCheckBox, QInputDialog, QStackedWidget,
                            QDialog, QDialogButtonBox, QFormLayout, QToolButton)
from PyQt6.QtCore import Qt, QDateTime, QSize, QPropertyAnimation, QEasingCurve, QTimer, pyqtProperty
from PyQt6.QtGui import QPalette, QAction, QLinearGradient, QGradient, QColor
from groq import Groq
from speech_to_text import SpeechWorker
from note_item import NoteItem
from handwritten_processor import extract_handwritten_text, summarize_handwritten_text
from note_storage import save_notes, load_notes
from chat_with_ai import ChatWithAIScreen
from datetime import datetime
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request
import io
import socket

GROQ_API_KEY = "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"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"
NOTES_FILE = "notes.json"
GUEST_USERS_FILE = "guest_users.json"
DRIVE_FILE_NAME = "noteflow_notes.json"

SCOPES = [
    'openid',  
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/drive.file'
]

def log_ai_activity(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[AI Activity] {timestamp} - {message}")

def is_connected():
    try:
        socket.create_connection(("www.google.com", 80))
        return True
    except OSError:
        return False

def get_drive_service(creds):
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(creds):
    if not is_connected():
        print("No internet connection; skipping Google Drive upload")
        return
    try:
        drive_service = get_drive_service(creds)
        query = f"name='{DRIVE_FILE_NAME}' and trashed=false"
        response = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        media = MediaFileUpload(NOTES_FILE, mimetype='application/json')
        if files:
            file_id = files[0]['id']
            drive_service.files().update(fileId=file_id, media_body=media).execute()
            print(f"Updated {DRIVE_FILE_NAME} on Google Drive (File ID: {file_id})")
        else:
            file_metadata = {'name': DRIVE_FILE_NAME}
            drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"Uploaded {DRIVE_FILE_NAME} to Google Drive")
    except Exception as e:
        print(f"Error uploading to Google Drive: {str(e)}")

def download_from_drive(creds):
    if not is_connected():
        print("No internet connection; cannot download from Google Drive")
        return False
    try:
        drive_service = get_drive_service(creds)
        query = f"name='{DRIVE_FILE_NAME}' and trashed=false"
        response = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = response.get('files', [])
        if not files:
            print(f"No {DRIVE_FILE_NAME} found on Google Drive")
            return False
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.FileIO(NOTES_FILE, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Downloaded {int(status.progress() * 100)}%")
        print(f"Downloaded {DRIVE_FILE_NAME} from Google Drive (File ID: {file_id})")
        return True
    except Exception as e:
        print(f"Error downloading from Google Drive: {str(e)}")
        return False

class DeleteConfirmationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Delete User Data")
        layout = QVBoxLayout(self)
        self.label = QLabel("Are you sure you want to delete all user data? This action cannot be undone.")
        layout.addWidget(self.label)
        self.confirm_checkbox = QCheckBox("I understand that this will delete all notes and cannot be undone.")
        layout.addWidget(self.confirm_checkbox)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def accept(self):
        if self.confirm_checkbox.isChecked():
            super().accept()
        else:
            self.label.setText("Please check the box to confirm deletion.")

class GuestLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Guest Account")
        self.layout = QFormLayout(self)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter your name")
        self.layout.addRow("Name:", self.name_input)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email")
        self.email_input.textChanged.connect(self.validate_email)
        self.layout.addRow("Email:", self.email_input)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password (6+ chars)")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.textChanged.connect(self.validate_password)
        self.layout.addRow("Password:", self.password_input)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("Confirm your password")
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input.textChanged.connect(self.validate_password)
        self.layout.addRow("Confirm Password:", self.confirm_password_input)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)
        self.login_button = QPushButton("Already have an account? Log In")
        self.login_button.clicked.connect(self.switch_to_login)
        self.layout.addWidget(self.login_button)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        self.layout.addWidget(self.error_label)
        self.user_info = None
        self.is_login_mode = False

    def validate_email(self):
        email = self.email_input.text().strip()
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not email:
            self.email_input.setStyleSheet("border: 1px solid red;")
        elif not re.match(email_regex, email):
            self.email_input.setStyleSheet("border: 1px solid orange;")
        else:
            self.email_input.setStyleSheet("border: 1px solid green;")

    def validate_password(self):
        password = self.password_input.text()
        confirm = self.confirm_password_input.text()
        if not password:
            self.password_input.setStyleSheet("border: 1px solid red;")
        elif len(password) < 6:
            self.password_input.setStyleSheet("border: 1px solid orange;")
        else:
            self.password_input.setStyleSheet("border: 1px solid green;")
        if not confirm:
            self.confirm_password_input.setStyleSheet("border: 1px solid red;")
        elif confirm != password:
            self.confirm_password_input.setStyleSheet("border: 1px solid orange;")
        else:
            self.confirm_password_input.setStyleSheet("border: 1px solid green;")

    def validate_and_accept(self):
        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        try:
            if os.path.exists(GUEST_USERS_FILE):
                with open(GUEST_USERS_FILE, 'r') as f:
                    guest_users = json.load(f)
            else:
                guest_users = []
        except Exception as e:
            self.error_label.setText(f"Error accessing user data: {str(e)}")
            return
        if self.is_login_mode:
            if not email or not password:
                self.error_label.setText("Email and password are required.")
                return
            for user in guest_users:
                if user['email'] == email and user['password'] == password:
                    self.user_info = {'name': user['name'], 'email': email}
                    log_ai_activity(f"Guest user logged in: {email}")
                    super().accept()
                    return
            self.error_label.setText("Invalid email or password.")
            return
        if not name or not email or not password or not confirm_password:
            self.error_label.setText("All fields are required.")
            return
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            self.error_label.setText("Invalid email format.")
            return
        if password != confirm_password:
            self.error_label.setText("Passwords do not match.")
            return
        if len(password) < 6:
            self.error_label.setText("Password must be at least 6 characters long.")
            return
        for user in guest_users:
            if user['email'] == email:
                self.error_label.setText("Email already exists. Try logging in.")
                return
        new_user = {'name': name, 'email': email, 'password': password}
        guest_users.append(new_user)
        try:
            with open(GUEST_USERS_FILE, 'w') as f:
                json.dump(guest_users, f, indent=4)
            self.user_info = new_user
            log_ai_activity(f"New guest user created: {name} ({email})")
            super().accept()
        except Exception as e:
            self.error_label.setText(f"Error saving user: {str(e)}")

    def switch_to_login(self):
        self.is_login_mode = True
        self.setWindowTitle("Log In to Guest Account")
        self.name_input.setVisible(False)
        self.confirm_password_input.setVisible(False)
        self.layout.labelForField(self.name_input).setVisible(False)
        self.layout.labelForField(self.confirm_password_input).setVisible(False)
        self.login_button.setText("Need an account? Sign Up")
        self.login_button.clicked.disconnect()
        self.login_button.clicked.connect(self.switch_to_signup)
        self.error_label.setText("")

    def switch_to_signup(self):
        self.is_login_mode = False
        self.setWindowTitle("Create Guest Account")
        self.name_input.setVisible(True)
        self.confirm_password_input.setVisible(True)
        self.layout.labelForField(self.name_input).setVisible(True)
        self.layout.labelForField(self.confirm_password_input).setVisible(True)
        self.login_button.setText("Already have an account? Log In")
        self.login_button.clicked.disconnect()
        self.login_button.clicked.connect(self.switch_to_login)
        self.error_label.setText("")

class LoginScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel("NoteFlow - Sign In")
        title_label.setObjectName("appTitle")
        self.layout.addWidget(title_label)
        self.sign_in_button = QPushButton("Sign in with Google")
        self.sign_in_button.clicked.connect(self.google_sign_in)
        self.layout.addWidget(self.sign_in_button)
        self.guest_sign_in_button = QPushButton("Sign in as Guest")
        self.guest_sign_in_button.clicked.connect(self.guest_sign_in)
        self.layout.addWidget(self.guest_sign_in_button)
        self.status_label = QLabel("Please sign in to continue.")
        self.status_label.setObjectName("statusLabel")
        self.layout.addWidget(self.status_label)
        self.user_info = None

    def google_sign_in(self):
        try:
            creds = None
            if os.path.exists(TOKEN_FILE):
                try:
                    with open(TOKEN_FILE, 'rb') as token:
                        creds = pickle.load(token)
                    log_ai_activity(f"Loaded existing token with scopes: {creds.scopes}")
                except Exception as e:
                    log_ai_activity(f"Error loading token.pickle: {str(e)}")
                    creds = None
            if creds and set(creds.scopes) != set(SCOPES):
                log_ai_activity(f"Scopes mismatch detected. Stored: {creds.scopes}, Requested: {SCOPES}")
                try:
                    os.remove(TOKEN_FILE)
                    log_ai_activity("Deleted token.pickle due to scope change")
                except Exception as e:
                    log_ai_activity(f"Error deleting token.pickle: {str(e)}")
                creds = None
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        log_ai_activity("Refreshed expired token")
                    except Exception as e:
                        log_ai_activity(f"Error refreshing token: {str(e)}")
                        creds = None
                if not creds:
                    log_ai_activity(f"Requesting new credentials with scopes: {SCOPES}")
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)
                    log_ai_activity("New credentials obtained")
                try:
                    with open(TOKEN_FILE, 'wb') as token:
                        pickle.dump(creds, token)
                    log_ai_activity("Saved new token to token.pickle")
                except Exception as e:
                    log_ai_activity(f"Error saving token.pickle: {str(e)}")
            main_window = self.parent().parent().parent()
            main_window.google_creds = creds
            main_window.is_guest = False
            service = build('people', 'v1', credentials=creds)
            profile = service.people().get(resourceName='people/me', personFields='names,emailAddresses').execute()
            user_name = profile.get('names', [{}])[0].get('displayName', 'Unknown User')
            user_email = profile.get('emailAddresses', [{}])[0].get('value', 'Unknown Email')
            self.user_info = {'name': user_name, 'email': user_email}
            self.status_label.setText(f"Logged in as {user_name} ({user_email})")
            log_ai_activity(f"User logged in: {user_name} ({user_email})")
            if not os.path.exists(NOTES_FILE):
                if download_from_drive(creds):
                    log_ai_activity("Fetched notes from Google Drive after login")
                    main_window.notes_screen.load_saved_notes()
                else:
                    log_ai_activity("No notes found on Google Drive; starting fresh")
            main_window.set_user_info(self.user_info)
            main_window.show_welcome_screen()
        except Exception as e:
            error_msg = str(e)
            log_ai_activity(f"Google sign-in failed: {error_msg}")
            if "access_denied" in error_msg.lower():
                self.status_label.setText(
                    "Access denied: Your account is not authorized. Contact the developer to be added as a test user."
                )
            else:
                self.status_label.setText(f"Sign-in error: {error_msg}")

    def guest_sign_in(self):
        dialog = GuestLoginDialog(self)
        if dialog.exec():
            self.user_info = dialog.user_info
            self.status_label.setText(f"Logged in as Guest: {self.user_info['name']} ({self.user_info['email']})")
            log_ai_activity(f"Guest user logged in: {self.user_info['name']} ({self.user_info['email']})")
            main_window = self.parent().parent().parent()
            main_window.google_creds = None  
            main_window.is_guest = True  
            main_window.set_user_info(self.user_info)
            main_window.show_welcome_screen()

class WelcomeScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel("NoteFlow")
        title_label.setObjectName("appTitle")
        self.layout.addWidget(title_label)
        self.notes_button = QPushButton("📝 Notes")
        self.handwritten_button = QPushButton("✍️ Handwritten")
        self.chat_with_ai_button = QPushButton("🎤 Chat with AI")
        self.quit_button = QPushButton("🚪 Quit")
        self.notes_button.clicked.connect(self.show_notes_screen)
        self.handwritten_button.clicked.connect(self.show_handwritten_screen)
        self.chat_with_ai_button.clicked.connect(self.show_chat_with_ai_screen)
        self.quit_button.clicked.connect(self.quit_app)
        self.layout.addWidget(self.notes_button)
        self.layout.addWidget(self.handwritten_button)
        self.layout.addWidget(self.chat_with_ai_button)
        self.layout.addWidget(self.quit_button)

    def show_notes_screen(self):
        main_window = self.parent().parent().parent()
        main_window.show_notes_screen()

    def show_handwritten_screen(self):
        main_window = self.parent().parent().parent()
        main_window.show_handwritten_screen()

    def show_chat_with_ai_screen(self):
        main_window = self.parent().parent().parent()
        main_window.show_chat_with_ai_screen()

    def quit_app(self):
        log_ai_activity("Application quit via Quit button")
        QApplication.quit()

class NotesScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.notes = []
        self.archived_notes = []
        self.client = Groq(api_key=GROQ_API_KEY)
        self.current_note_index = None
        main_layout = QHBoxLayout(self)
        self.current_color = "#fff3e0"
        self.collaborators = []

        # Sidebar setup
        sidebar = QFrame()
        sidebar.setFixedWidth(320)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search notes...")
        self.search_bar.textChanged.connect(self.filter_notes)
        sidebar_layout.addWidget(self.search_bar)
        sidebar_title = QLabel("Table of Contents")
        sidebar_title.setObjectName("sidebarTitle")
        self.notes_list = QListWidget()
        self.notes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self.show_context_menu)
        self.notes_list.itemClicked.connect(self.load_note)
        sidebar_layout.addWidget(sidebar_title)
        sidebar_layout.addWidget(self.notes_list)
        sidebar.setObjectName("sidebar")
        main_layout.addWidget(sidebar)

        # Content area setup
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # Title input
        title_label = QLabel("Note Title")
        title_label.setObjectName("sectionLabel")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Enter note title...")
        content_layout.addWidget(title_label)
        content_layout.addWidget(self.title_input)

        # Text editor
        input_label = QLabel("Your Note")
        input_label.setObjectName("sectionLabel")
        content_layout.addWidget(input_label)
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Type your note here or use the checklist below...")
        self.input_text.setMinimumHeight(100)
        content_layout.addWidget(self.input_text)

        # Checklist
        checklist_label = QLabel("Checklist (Optional)")
        checklist_label.setObjectName("sectionLabel")
        self.checklist_layout = QVBoxLayout()
        self.checklist_items = []
        add_checklist_item_btn = QPushButton("Add Checklist Item")
        add_checklist_item_btn.clicked.connect(self.add_checklist_item)
        content_layout.addWidget(checklist_label)
        content_layout.addLayout(self.checklist_layout)
        content_layout.addWidget(add_checklist_item_btn)

        # Toolbar with QToolButtons
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(5)

        self.back_toolbutton = QToolButton()
        self.back_toolbutton.setText("⬅️")
        self.back_toolbutton.setToolTip("Back")
        self.back_toolbutton.setFixedSize(40, 40)
        self.back_toolbutton.clicked.connect(self.show_welcome_screen)
        toolbar_layout.addWidget(self.back_toolbutton)

        self.upload_toolbutton = QToolButton()
        self.upload_toolbutton.setText("📂")
        self.upload_toolbutton.setToolTip("Upload")
        self.upload_toolbutton.setFixedSize(40, 40)
        self.upload_toolbutton.clicked.connect(self.upload_note)
        toolbar_layout.addWidget(self.upload_toolbutton)

        self.record_toolbutton = QToolButton()
        self.record_toolbutton.setText("🎤")
        self.record_toolbutton.setToolTip("Record")
        self.record_toolbutton.setFixedSize(40, 40)
        self.record_toolbutton.clicked.connect(self.start_recording)
        toolbar_layout.addWidget(self.record_toolbutton)

        self.stop_toolbutton = QToolButton()
        self.stop_toolbutton.setText("⏹️")
        self.stop_toolbutton.setToolTip("Stop")
        self.stop_toolbutton.setFixedSize(40, 40)
        self.stop_toolbutton.clicked.connect(self.stop_recording)
        self.stop_toolbutton.setVisible(False)
        toolbar_layout.addWidget(self.stop_toolbutton)

        self.ai_response_toolbutton = QToolButton()
        self.ai_response_toolbutton.setText("🤖")
        self.ai_response_toolbutton.setToolTip("AI Response")
        self.ai_response_toolbutton.setFixedSize(40, 40)
        self.ai_response_toolbutton.clicked.connect(self.generate_ai_response)
        toolbar_layout.addWidget(self.ai_response_toolbutton)

        self.autotag_toolbutton = QToolButton()
        self.autotag_toolbutton.setText("🏷️")
        self.autotag_toolbutton.setToolTip("Autotag")
        self.autotag_toolbutton.setFixedSize(40, 40)
        self.autotag_toolbutton.clicked.connect(self.autotag_note)
        toolbar_layout.addWidget(self.autotag_toolbutton)

        self.manual_tag_toolbutton = QToolButton()
        self.manual_tag_toolbutton.setText("🔖")
        self.manual_tag_toolbutton.setToolTip("Manual Tag")
        self.manual_tag_toolbutton.setFixedSize(40, 40)
        self.manual_tag_toolbutton.clicked.connect(self.manual_tag)
        toolbar_layout.addWidget(self.manual_tag_toolbutton)

        self.organize_toolbutton = QToolButton()
        self.organize_toolbutton.setText("🧠")
        self.organize_toolbutton.setToolTip("Organize & Ideas")
        self.organize_toolbutton.setFixedSize(40, 40)
        self.organize_toolbutton.clicked.connect(self.organize_and_generate_ideas)
        toolbar_layout.addWidget(self.organize_toolbutton)

        self.reminder_toolbutton = QToolButton()
        self.reminder_toolbutton.setText("⏰")
        self.reminder_toolbutton.setToolTip("Reminder")
        self.reminder_toolbutton.setFixedSize(40, 40)
        self.reminder_toolbutton.clicked.connect(self.set_reminder)
        toolbar_layout.addWidget(self.reminder_toolbutton)

        self.attach_toolbutton = QToolButton()
        self.attach_toolbutton.setText("📎")
        self.attach_toolbutton.setToolTip("Attach File")
        self.attach_toolbutton.setFixedSize(40, 40)
        self.attach_toolbutton.clicked.connect(self.attach_file)
        toolbar_layout.addWidget(self.attach_toolbutton)

        self.save_toolbutton = QToolButton()
        self.save_toolbutton.setText("💾")
        self.save_toolbutton.setToolTip("Save")
        self.save_toolbutton.setFixedSize(40, 40)
        self.save_toolbutton.clicked.connect(self.save_note)
        toolbar_layout.addWidget(self.save_toolbutton)

        self.clear_toolbutton = QToolButton()
        self.clear_toolbutton.setText("🗑️")
        self.clear_toolbutton.setToolTip("Clear")
        self.clear_toolbutton.setFixedSize(40, 40)
        self.clear_toolbutton.clicked.connect(self.clear_text)
        toolbar_layout.addWidget(self.clear_toolbutton)

        content_layout.addLayout(toolbar_layout)

        # Recording bar and AI insights
        self.recording_bar = QProgressBar()
        self.recording_bar.setVisible(False)
        self.recording_bar.setMaximum(0)
        content_layout.addWidget(self.recording_bar)

        response_label = QLabel("AI Insights")
        response_label.setObjectName("sectionLabel")
        content_layout.addWidget(response_label)
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("AI insights will appear here...")
        content_layout.addWidget(self.response_text)

        main_layout.addWidget(content_widget)

        # Initialize other attributes
        self.speech_worker = None
        self.current_tags = ""
        self.current_reminder = None
        self.attached_files = []
        self.drawing = ""
        self.load_saved_notes()
        self.update_notes_list()

    def show_welcome_screen(self):
        main_window = self.parent().parent().parent()
        main_window.show_welcome_screen()

    def load_saved_notes(self):
        try:
            self.notes, self.archived_notes = load_notes()
            # Fix tuple length inconsistency
            for i, note in enumerate(self.notes):
                if len(note) < 10:
                    self.notes[i] = note + ("",) * (10 - len(note))
            for i, note in enumerate(self.archived_notes):
                if len(note) < 10:
                    self.archived_notes[i] = note + ("",) * (10 - len(note))
        except Exception as e:
            self.response_text.setText(f"Error loading notes: {str(e)}")

    def show_context_menu(self, position):
        item = self.notes_list.itemAt(position)
        if not item:
            return
        index = self.notes_list.row(item)
        menu = QMenu()
        pin_action = QAction("Pin/Unpin", self)
        archive_action = QAction("Archive/Unarchive", self)
        delete_action = QAction("Delete", self)
        edit_tags_action = QAction("Edit Tags", self)
        pin_action.triggered.connect(lambda: self.pin_note(index))
        archive_action.triggered.connect(lambda: self.archive_note(index))
        delete_action.triggered.connect(lambda: self.delete_note(index))
        edit_tags_action.triggered.connect(lambda: self.edit_tags(index))
        menu.addAction(pin_action)
        menu.addAction(archive_action)
        menu.addAction(delete_action)
        menu.addAction(edit_tags_action)
        menu.exec(self.notes_list.mapToGlobal(position))

    def pin_note(self, index):
        try:
            note = list(self.notes.pop(index))
            note[4] = not note[4]  # Toggle pinned
            if note[4]:
                self.notes.insert(0, tuple(note))
            else:
                self.notes.append(tuple(note))
            self.update_notes_list()
        except Exception as e:
            self.response_text.setText(f"Error pinning note: {str(e)}")

    def archive_note(self, index):
        try:
            note = list(self.notes.pop(index))
            note[5] = not note[5]  # Toggle archived
            if note[5]:
                self.archived_notes.append(tuple(note))
            else:
                self.notes.append(tuple(note))
            self.update_notes_list()
        except Exception as e:
            self.response_text.setText(f"Error archiving note: {str(e)}")

    def delete_note(self, index):
        try:
            self.notes.pop(index)
            self.update_notes_list()
        except Exception as e:
            self.response_text.setText(f"Error deleting note: {str(e)}")

    def edit_tags(self, index):
        try:
            note = list(self.notes[index])
            new_tags, ok = QInputDialog.getText(self, "Edit Tags", "Enter new tags (comma-separated):", text=note[3])
            if ok:
                note[3] = new_tags
                self.notes[index] = tuple(note)
                self.update_notes_list()
        except Exception as e:
            self.response_text.setText(f"Error editing tags: {str(e)}")

    def filter_notes(self):
        try:
            search_text = self.search_bar.text().lower()
            self.notes_list.clear()
            for note in self.notes:
                title, content, color, tags, pinned, archived, reminder, attached_files, collaborators, drawing = note
                if archived:
                    continue
                if (search_text in title.lower() or search_text in content.lower() or search_text in tags.lower()):
                    note_widget = NoteItem(title, content, color, tags, pinned, archived, reminder, attached_files, collaborators, drawing)
                    item = QListWidgetItem()
                    item.setSizeHint(QSize(300, 150))
                    self.notes_list.addItem(item)
                    self.notes_list.setItemWidget(item, note_widget)
        except Exception as e:
            self.response_text.setText(f"Error filtering notes: {str(e)}")

    def upload_note(self):
        try:
            file_name, _ = QFileDialog.getOpenFileName(self, "Upload Note", "", "Text Files (*.txt)")
            if file_name:
                with open(file_name, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.input_text.setText(content)
        except Exception as e:
            self.response_text.setText(f"Error uploading file: {str(e)}")

    def start_recording(self):
        try:
            self.record_toolbutton.setVisible(False)
            self.stop_toolbutton.setVisible(True)
            self.input_text.setText("Listening...")
            self.recording_bar.setVisible(True)
            self.speech_worker = SpeechWorker()
            self.speech_worker.speech_result.connect(self.handle_speech_result)
            self.speech_worker.recording_update.connect(self.update_recording_ui)
            self.speech_worker.finished.connect(self.recording_finished)
            self.speech_worker.start()
        except Exception as e:
            self.response_text.setText(f"Error starting recording: {str(e)}")

    def stop_recording(self):
        try:
            if self.speech_worker and self.speech_worker.isRunning():
                self.speech_worker.stop()
                self.speech_worker.quit()
                self.speech_worker.wait()
                self.speech_worker = None
            self.recording_finished()
        except Exception as e:
            self.response_text.setText(f"Error stopping recording: {str(e)}")

    def update_recording_ui(self):
        self.input_text.setText("Recording... Speak now!")

    def handle_speech_result(self, text):
        self.input_text.setText(text)
        self.generate_ai_response()

    def recording_finished(self):
        try:
            self.record_toolbutton.setVisible(True)
            self.stop_toolbutton.setVisible(False)
            self.recording_bar.setVisible(False)
            if self.input_text.toPlainText() in ["Listening...", "Recording... Speak now!"]:
                self.input_text.setText("")
            QApplication.processEvents()
        except Exception as e:
            self.response_text.setText(f"Error finishing recording: {str(e)}")

    def generate_ai_response(self):
        note_content = self.input_text.toPlainText()
        if not note_content.strip():
            self.response_text.setText("Please enter a note to generate an AI response.")
            return
        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant for taking notes."},
                    {"role": "user", "content": note_content}
                ],
                max_tokens=500
            )
            ai_response = response.choices[0].message.content
            self.response_text.setText(ai_response)
            log_ai_activity(f"Generated AI response for note: {note_content[:50]}...")
        except Exception as e:
            self.response_text.setText(f"Error getting AI response: {str(e)}")

    def autotag_note(self):
        note_content = self.input_text.toPlainText()
        if not note_content.strip():
            self.response_text.setText("Please enter a note to tag.")
            return
        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are an AI that categorizes notes. Suggest 1-3 relevant tags for the given note content."},
                    {"role": "user", "content": f"Note: {note_content}\nSuggest tags for this note."}
                ],
                max_tokens=100
            )
            tags = response.choices[0].message.content.strip()
            self.current_tags = tags
            self.response_text.setText(f"Suggested Tags: {tags}")
        except Exception as e:
            self.response_text.setText(f"Error tagging note: {str(e)}")

    def manual_tag(self):
        try:
            tags, ok = QInputDialog.getText(self, "Manual Tag", "Enter tags (comma-separated):")
            if ok and tags:
                self.current_tags = tags
                self.response_text.setText(f"Manually Added Tags: {tags}")
        except Exception as e:
            self.response_text.setText(f"Error adding manual tags: {str(e)}")

    def organize_and_generate_ideas(self):
        note_content = self.input_text.toPlainText()
        if not note_content.strip():
            self.response_text.setText("Please enter a note to organize and generate ideas.")
            return
        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are an AI that organizes notes and generates related ideas. First, summarize or reformat the note for clarity, then suggest 2-3 related ideas."},
                    {"role": "user", "content": f"Note: {note_content}\nOrganize this note and generate related ideas."}
                ],
                max_tokens=500
            )
            result = response.choices[0].message.content.strip()
            self.response_text.setText(result)
            self.input_text.setText(result.split("Ideas:")[0].strip() if "Ideas:" in result else result)
        except Exception as e:
            self.response_text.setText(f"Error organizing note: {str(e)}")

    def set_reminder(self):
        try:
            dialog = QDateTimeEdit(self)
            dialog.setCalendarPopup(True)
            dialog.setDateTime(QDateTime.currentDateTime())
            dialog.setMinimumDateTime(QDateTime.currentDateTime())
            dialog.setDisplayFormat("yyyy-MM-dd HH:mm")
            if dialog.exec():
                self.current_reminder = dialog.dateTime()
                self.response_text.setText(f"Reminder set for: {self.current_reminder.toString('yyyy-MM-dd HH:mm')}")
        except Exception as e:
            self.response_text.setText(f"Error setting reminder: {str(e)}")

    def attach_file(self):
        try:
            file_name, _ = QFileDialog.getOpenFileName(self, "Attach File", "", "All Files (*.*)")
            if file_name:
                self.attached_files.append(file_name)
                self.response_text.setText(f"Attached: {', '.join(self.attached_files)}")
        except Exception as e:
            self.response_text.setText(f"Error attaching file: {str(e)}")

    def add_checklist_item(self):
        try:
            item_layout = QHBoxLayout()
            checkbox = QCheckBox()
            item_text = QLineEdit()
            item_text.setPlaceholderText("Enter checklist item...")
            item_layout.addWidget(checkbox)
            item_layout.addWidget(item_text)
            self.checklist_layout.addLayout(item_layout)
            self.checklist_items.append((checkbox, item_text))
        except Exception as e:
            self.response_text.setText(f"Error adding checklist item: {str(e)}")

    def save_note(self):
        try:
            title = self.title_input.text().strip() or "Untitled"
            content = self.input_text.toPlainText()
            checklist_content = ""
            for checkbox, item_text in self.checklist_items:
                checked = "☑" if checkbox.isChecked() else "☐"
                checklist_content += f"{checked} {item_text.text()}\n"
            if checklist_content:
                content += "\n\nChecklist:\n" + checklist_content
            if content.strip():
                if self.current_note_index is not None:
                    self.notes[self.current_note_index] = (
                        title, content, self.current_color, self.current_tags,
                        self.notes[self.current_note_index][4],  # pinned
                        self.notes[self.current_note_index][5],  # archived
                        self.current_reminder, self.attached_files, self.collaborators, self.drawing
                    )
                else:
                    self.notes.append((
                        title, content, self.current_color, self.current_tags,
                        False, False, self.current_reminder, self.attached_files, self.collaborators, self.drawing
                    ))
                self.current_note_index = None
                self.update_notes_list()
                self.current_tags = ""
                self.current_reminder = None
                self.attached_files = []
                self.clear_text()
        except Exception as e:
            self.response_text.setText(f"Error saving note: {str(e)}")

    def update_notes_list(self):
        try:
            self.notes_list.clear()
            sorted_notes = sorted(self.notes, key=lambda x: x[4], reverse=True)  # Sort by pinned
            for note in sorted_notes:
                title, content, color, tags, pinned, archived, reminder, attached_files, collaborators, drawing = note
                if archived:
                    continue
                note_widget = NoteItem(title, content, color, tags, pinned, archived, reminder, attached_files, collaborators, drawing)
                item = QListWidgetItem()
                item.setSizeHint(QSize(300, 150))
                self.notes_list.addItem(item)
                self.notes_list.setItemWidget(item, note_widget)
            self.notes_list.repaint()
        except Exception as e:
            self.response_text.setText(f"Error updating notes list: {str(e)}")

    def load_note(self, item):
        try:
            index = self.notes_list.row(item)
            self.current_note_index = index
            title, content, color, tags, _, _, reminder, attached_files, collaborators, drawing = self.notes[index]
            self.title_input.setText(title)
            self.input_text.setText(content.split("Checklist:")[0].strip() if "Checklist:" in content else content)
            self.response_text.setText("")
            self.current_color = color
            self.current_tags = tags
            self.current_reminder = reminder
            self.attached_files = attached_files if attached_files else []
            self.collaborators = collaborators if collaborators else []
            self.drawing = drawing
            palette = self.input_text.palette()
            palette.setColor(QPalette.ColorRole.Base, QColor(color))
            self.input_text.setPalette(palette)
            self.response_text.setPalette(palette)
            for i in range(self.checklist_layout.count()):
                layout = self.checklist_layout.itemAt(i)
                if layout:
                    for j in range(layout.count()):
                        widget = layout.itemAt(j).widget()
                        if widget:
                            widget.deleteLater()
            self.checklist_items.clear()
            if "Checklist:" in content:
                checklist_part = content.split("Checklist:")[1].strip()
                for line in checklist_part.split("\n"):
                    if line.strip():
                        checked = line.startswith("☑")
                        text = line[2:].strip()
                        self.add_checklist_item()
                        checkbox, item_text = self.checklist_items[-1]
                        checkbox.setChecked(checked)
                        item_text.setText(text)
        except Exception as e:
            self.response_text.setText(f"Error loading note: {str(e)}")

    def clear_text(self):
        try:
            self.title_input.clear()
            self.input_text.clear()
            self.response_text.clear()
            self.current_tags = ""
            self.current_reminder = None
            self.attached_files = []
            self.drawing = ""
            for i in range(self.checklist_layout.count()):
                layout = self.checklist_layout.itemAt(i)
                if layout:
                    for j in range(layout.count()):
                        widget = layout.itemAt(j).widget()
                        if widget:
                            widget.deleteLater()
            self.checklist_items.clear()
            self.current_note_index = None
        except Exception as e:
            self.response_text.setText(f"Error clearing text: {str(e)}")

class HandwrittenScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.back_button = QPushButton("⬅️ Back")
        self.back_button.clicked.connect(self.show_welcome_screen)
        layout.addWidget(self.back_button)
        self.extract_button = QPushButton("📝 Extract Handwritten Text")
        self.summarize_button = QPushButton("📋 Summarize Handwritten")
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Extracted handwritten text will appear here...")
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("Summary or status messages will appear here...")
        self.extract_button.clicked.connect(self.extract_handwritten)
        self.summarize_button.clicked.connect(self.summarize_handwritten)
        layout.addWidget(self.extract_button)
        layout.addWidget(self.summarize_button)
        layout.addWidget(self.input_text)
        layout.addWidget(self.response_text)

    def show_welcome_screen(self):
        main_window = self.parent().parent().parent()
        main_window.show_welcome_screen()

    def extract_handwritten(self):
        try:
            file_name, _ = QFileDialog.getOpenFileName(self, "Upload Handwritten Note", "", "Images and PDFs (*.png *.jpg *.jpeg *.pdf)")
            if file_name:
                extracted_text = extract_handwritten_text(file_name)
                self.input_text.setText(extracted_text)
                self.response_text.setText("Handwritten text extracted successfully.")
        except Exception as e:
            self.response_text.setText(f"Error extracting handwritten text: {str(e)}")

    def summarize_handwritten(self):
        try:
            note_content = self.input_text.toPlainText()
            if not note_content.strip():
                self.response_text.setText("Please extract handwritten text first.")
                return
            client = Groq(api_key=GROQ_API_KEY)
            summary = summarize_handwritten_text(note_content, client)
            self.response_text.setText(f"Summary:\n{summary}")
        except Exception as e:
            self.response_text.setText(f"Error summarizing handwritten text: {str(e)}")

class DrawingScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.back_button = QPushButton("⬅️ Back")
        self.back_button.clicked.connect(self.show_welcome_screen)
        layout.addWidget(self.back_button)
        self.drawing_desc = QTextEdit()
        self.drawing_desc.setPlaceholderText("Describe your drawing here...")
        self.add_button = QPushButton("✍️ Add Drawing")
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("Drawing description will appear here...")
        self.add_button.clicked.connect(self.add_drawing)
        layout.addWidget(self.drawing_desc)
        layout.addWidget(self.add_button)
        layout.addWidget(self.response_text)

    def show_welcome_screen(self):
        main_window = self.parent().parent().parent()
        main_window.show_welcome_screen()

    def add_drawing(self):
        try:
            drawing_desc = self.drawing_desc.toPlainText()
            if drawing_desc:
                self.response_text.setText(f"Drawing: {drawing_desc}")
            else:
                self.response_text.setText("Please describe your drawing.")
        except Exception as e:
            self.response_text.setText(f"Error adding drawing: {str(e)}")

class NotesApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NoteFlow")
        self.setGeometry(100, 100, 1000, 700)
        self.animation = None
        self.user_info = None
        self.google_creds = None
        self.is_guest = False
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self.main_widget)
        layout.addWidget(self.stack)
        self.login_screen = LoginScreen(self)
        self.welcome_screen = WelcomeScreen(self)
        self.notes_screen = NotesScreen(self)
        self.handwritten_screen = HandwrittenScreen(self)
        self.drawing_screen = DrawingScreen(self)
        self.chat_with_ai_screen = ChatWithAIScreen(self)
        self.stack.addWidget(self.login_screen)
        self.stack.addWidget(self.welcome_screen)
        self.stack.addWidget(self.notes_screen)
        self.stack.addWidget(self.handwritten_screen)
        self.stack.addWidget(self.drawing_screen)
        self.stack.addWidget(self.chat_with_ai_screen)
        self.show_login_screen()
        try:
            with open("styles.qss", "r") as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print("styles.qss file not found.")
        self.start_gradient_animation()

    def start_gradient_animation(self):
        self.gradient = QLinearGradient(0, 0, self.width(), self.height())
        self.gradient.setColorAt(0, QColor("#4A90E2"))
        self.gradient.setColorAt(1, QColor("#E76BEB"))
        self.animation = QPropertyAnimation(self, b"gradient_position")
        self.animation.setDuration(5000)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setLoopCount(-1)
        self.animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.animation.valueChanged.connect(self.update_gradient)
        self.animation.start()
        self.resizeEvent = self.on_resize

    def on_resize(self, event):
        self.gradient.setFinalStop(self.width(), self.height())
        self.update_gradient(self.animation.currentValue())
        super().resizeEvent(event)

    def update_gradient(self, value):
        color1 = QColor("#4A90E2")
        color2 = QColor("#E76BEB")
        color3 = QColor("#6AB7F5")
        if value < 0.5:
            t = value * 2
            r = int(color1.red() + (color3.red() - color1.red()) * t)
            g = int(color1.green() + (color3.green() - color1.green()) * t)
            b = int(color1.blue() + (color3.blue() - color1.blue()) * t)
            start_color = QColor(r, g, b)
            end_color = color3
        else:
            t = (value - 0.5) * 2
            r = int(color3.red() + (color2.red() - color3.red()) * t)
            g = int(color3.green() + (color2.green() - color3.green()) * t)
            b = int(color3.blue() + (color2.blue() - color3.blue()) * t)
            start_color = color3
            end_color = QColor(r, g, b)
        self.gradient.setColorAt(0, start_color)
        self.gradient.setColorAt(1, end_color)
        palette = self.palette()
        palette.setBrush(QPalette.ColorRole.Window, self.gradient)
        self.setPalette(palette)

    def get_gradient_position(self):
        return self.animation.currentValue() if self.animation else 0.0

    def set_gradient_position(self, value):
        pass

    gradient_position = pyqtProperty(float, get_gradient_position, set_gradient_position)

    def show_login_screen(self):
        self.stack.setCurrentWidget(self.login_screen)

    def show_welcome_screen(self):
        self.stack.setCurrentWidget(self.welcome_screen)

    def show_notes_screen(self):
        self.stack.setCurrentWidget(self.notes_screen)

    def show_handwritten_screen(self):
        self.stack.setCurrentWidget(self.handwritten_screen)

    def show_drawing_screen(self):
        self.stack.setCurrentWidget(self.drawing_screen)

    def show_chat_with_ai_screen(self):
        self.stack.setCurrentWidget(self.chat_with_ai_screen)

    def set_user_info(self, user_info):
        self.user_info = user_info

    def closeEvent(self, event):
        try:
            save_notes(self.notes_screen.notes, self.notes_screen.archived_notes)
            if not self.is_guest and self.google_creds:
                upload_to_drive(self.google_creds)
            if self.notes_screen.speech_worker and self.notes_screen.speech_worker.isRunning():
                self.notes_screen.speech_worker.stop()
                self.notes_screen.speech_worker.quit()
                self.notes_screen.speech_worker.wait()
            event.accept()
        except Exception as e:
            print(f"Error closing app: {str(e)}")
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NotesApp()
    window.show()
    sys.exit(app.exec())