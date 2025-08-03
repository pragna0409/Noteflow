import speech_recognition as sr
import mtranslate as mt
from PyQt6.QtCore import QThread, pyqtSignal

class SpeechToTextTranslator:
    def __init__(self):
        self.input_language = "en"
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.is_recording = False

    def query_modifier(self, query):
        if not query:
            return "No speech detected."
        new_query = query.lower().strip()
        query_words = new_query.split()
        question_words = ["how", "where", "what", "who", "when", "why", "which", "whose", "whom", "can you", "What's", "where's", "how's"]
        if any(word + " " in new_query for word in question_words):
            new_query = new_query[:-1] + "?" if query_words[-1][-1] in ['.', '?', '!'] else new_query + "?"
        else:
            new_query = new_query[:-1] + "." if query_words[-1][-1] in ['.', '?', '!'] else new_query + "."
        return new_query.capitalize()

    def universal_translator(self, text):
        english_translation = mt.translate(text, "en", "auto")
        return english_translation.capitalize()

    def speech_recognition(self):
        with self.microphone as source:
            print("Listening...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self.is_recording = True
            try:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
            except sr.WaitTimeoutError:
                self.is_recording = False
                return "No speech detected within timeout."
            self.is_recording = False
        try:
            text = self.recognizer.recognize_google(audio, language=self.input_language)
            if self.input_language.lower() == "en" or "en" in self.input_language.lower():
                return self.query_modifier(text)
            else:
                return self.query_modifier(self.universal_translator(text))
        except sr.UnknownValueError:
            return "Could not understand audio."
        except sr.RequestError as e:
            return f"Could not request results; {str(e)}"

class SpeechWorker(QThread):
    speech_result = pyqtSignal(str)
    recording_update = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.translator = SpeechToTextTranslator()
        self.is_running = True

    def run(self):
        if not self.is_running:
            return
        if self.translator.is_recording:
            self.recording_update.emit()
        result = self.translator.speech_recognition()
        self.speech_result.emit(result)

    def stop(self):
        self.is_running = False
        self.translator.is_recording = False