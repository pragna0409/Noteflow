from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QProgressBar, QApplication
from PyQt6.QtCore import Qt, QDateTime
import re
from datetime import datetime
from speech_to_text import SpeechWorker
from groq import Groq

class ChatWithAIScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.client = Groq(api_key="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")
        self.back_button = QPushButton("⬅️ Back")
        self.back_button.clicked.connect(self.show_welcome_screen)
        self.layout.addWidget(self.back_button)
        self.record_button = QPushButton("🎤 Start Recording")
        self.stop_button = QPushButton("⏹️ Stop Recording")
        self.stop_button.setVisible(False)
        self.record_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.layout.addWidget(self.record_button)
        self.layout.addWidget(self.stop_button)
        self.recording_bar = QProgressBar()
        self.recording_bar.setVisible(False)
        self.recording_bar.setMaximum(0)
        self.layout.addWidget(self.recording_bar)
        self.speech_text = QTextEdit()
        self.speech_text.setReadOnly(True)
        self.speech_text.setPlaceholderText("Your spoken note or task will appear here...")
        self.layout.addWidget(self.speech_text)
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("AI responses or status messages will appear here...")
        self.layout.addWidget(self.response_text)
        self.speech_worker = None

    def show_welcome_screen(self):
        try:
            main_window = self.parent().parent().parent()
            main_window.show_welcome_screen()
        except AttributeError:
            self.response_text.setText("Error: Cannot navigate back.")

    def start_recording(self):
        if 'SpeechWorker' not in globals():
            self.response_text.setText("Error: Speech-to-text functionality unavailable.")
            return
        try:
            self.record_button.setVisible(False)
            self.stop_button.setVisible(True)
            self.speech_text.setText("Listening...")
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
            self.recording_finished()
        except Exception as e:
            self.response_text.setText(f"Error stopping recording: {str(e)}")

    def update_recording_ui(self):
        self.speech_text.setText("Recording... Speak now!")

    def handle_speech_result(self, text):
        self.speech_text.setText(text)
        self.process_spoken_text(text)
        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are Grok, a helpful AI assistant."},
                    {"role": "user", "content": text}
                ],
                max_tokens=500
            )
            ai_response = response.choices[0].message.content
            self.response_text.setText(ai_response)
        except Exception as e:
            self.response_text.setText(f"Error getting AI response: {str(e)}")

    def recording_finished(self):
        self.record_button.setVisible(True)
        self.stop_button.setVisible(False)
        self.recording_bar.setVisible(False)
        if self.speech_text.toPlainText() in ["Listening...", "Recording... Speak now!"]:
            self.speech_text.setText("")
        QApplication.processEvents()

    def process_spoken_text(self, text):
        text_lower = text.lower()
        if "make a note" in text_lower or "add a note" in text_lower:
            note_content = re.sub(r"(?i)(make a note|add a note)", "", text).strip()
            if note_content:
                self.save_spoken_note(note_content)
            else:
                self.response_text.setText("No note content provided.")
            return
        task_match = re.search(r"(?i)(I have to|I need to|I must)\s+(.+?)\s+(by|on|in|within)\s+(.+)", text)
        if task_match:
            task_description = task_match.group(2).strip()
            time_frame = task_match.group(4).strip().lower()
            self.create_task(task_description, time_frame, text)
            return
        self.save_spoken_note(text)

    def create_task(self, task_description, time_frame, full_text):
        try:
            task_name = " ".join(word.capitalize() for word in task_description.split())
            priority = self.determine_priority(time_frame)
            created_date_time = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm")
            task_content = (
                f"Task: {task_name}\n"
                f"Description: {full_text}\n"
                f"Created: {created_date_time}\n"
                f"Priority: {priority}\n"
                f"Checklist:\n☐ Complete {task_name}"
            )
            notes_screen = self.parent().parent().parent().notes_screen
            # Ensure 10-element tuple
            notes_screen.notes.append((
                f"Task: {task_name}", task_content, "#fff3e0", "task, " + priority.lower(),
                False, False, None, [], [], ""
            ))
            notes_screen.update_notes_list()
            self.response_text.setText(f"Task '{task_name}' created with priority '{priority}'.")
        except AttributeError:
            self.response_text.setText("Error: Cannot access NotesScreen.")

    def determine_priority(self, time_frame):
        time_frame = time_frame.lower()
        if "today" in time_frame:
            return "Very High"
        elif "tomorrow" in time_frame or "in a few days" in time_frame:
            return "High"
        elif "this month" in time_frame:
            return "Low"
        else:
            return "Medium"

    def save_spoken_note(self, content):
        try:
            if not content.strip():
                self.response_text.setText("No content recorded.")
                return
            notes_screen = self.parent().parent().parent().notes_screen
            # Ensure 10-element tuple
            notes_screen.notes.append((
                "Spoken Note", content, "#fff3e0", "", False, False, None, [], [], ""
            ))
            notes_screen.update_notes_list()
            self.response_text.setText("Spoken note saved.")
        except AttributeError:
            self.response_text.setText("Error: Cannot access NotesScreen.")