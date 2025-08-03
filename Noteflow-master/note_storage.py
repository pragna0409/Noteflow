import json
import os
from PyQt6.QtCore import QDateTime

NOTES_FILE = "notes.json"

def save_notes(notes, archived_notes):
    def serialize_note(note):
        try:
            title = note[0] if len(note) > 0 else "Untitled"
            content = note[1] if len(note) > 1 else ""
            color = note[2] if len(note) > 2 else "#fff3e0"
            tags = note[3] if len(note) > 3 else ""
            pinned = note[4] if len(note) > 4 else False
            archived = note[5] if len(note) > 5 else False
            reminder = note[6] if len(note) > 6 else None
            attached_files = note[7] if len(note) > 7 else []
            collaborators = note[8] if len(note) > 8 else []
            drawing = note[9] if len(note) > 9 else ""
            if reminder and hasattr(reminder, 'toString'):
                reminder = reminder.toString("yyyy-MM-dd HH:mm")
            elif reminder is None:
                reminder = ""
            return {
                "title": title,
                "content": content,
                "color": color,
                "tags": tags,
                "pinned": pinned,
                "archived": archived,
                "reminder": reminder,
                "attached_files": attached_files,
                "collaborators": collaborators,
                "drawing": drawing
            }
        except Exception as e:
            print(f"Error serializing note {note}: {str(e)}")
            return None

    serialized_notes = [serialize_note(note) for note in notes]
    serialized_archived_notes = [serialize_note(note) for note in archived_notes]
    serialized_notes = [n for n in serialized_notes if n is not None]
    serialized_archived_notes = [n for n in serialized_archived_notes if n is not None]
    data = {
        "notes": serialized_notes,
        "archived_notes": serialized_archived_notes
    }
    try:
        with open(NOTES_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print("Notes saved successfully to", NOTES_FILE)
    except Exception as e:
        print(f"Error saving notes to JSON: {str(e)}")

def load_notes():
    if not os.path.exists(NOTES_FILE):
        print(f"No notes file found at {NOTES_FILE}. Returning empty lists.")
        return [], []
    try:
        with open(NOTES_FILE, 'r') as f:
            data = json.load(f)

        def deserialize_note(note_data):
            if isinstance(note_data, list):
                title = note_data[0] if len(note_data) > 0 else "Untitled"
                content = note_data[1] if len(note_data) > 1 else ""
                color = note_data[2] if len(note_data) > 2 else "#fff3e0"
                tags = note_data[3] if len(note_data) > 3 else ""
                pinned = note_data[4] if len(note_data) > 4 else False
                archived = note_data[5] if len(note_data) > 5 else False
                reminder = note_data[6] if len(note_data) > 6 else None
                attached_files = note_data[7] if len(note_data) > 7 else []
                collaborators = note_data[8] if len(note_data) > 8 else []
                drawing = note_data[9] if len(note_data) > 9 else ""
            else:
                title = note_data.get("title", "Untitled")
                content = note_data.get("content", "")
                color = note_data.get("color", "#fff3e0")
                tags = note_data.get("tags", "")
                pinned = note_data.get("pinned", False)
                archived = note_data.get("archived", False)
                reminder = note_data.get("reminder", "")
                attached_files = note_data.get("attached_files", [])
                collaborators = note_data.get("collaborators", [])
                drawing = note_data.get("drawing", "")
            if reminder:
                reminder = QDateTime.fromString(reminder, "yyyy-MM-dd HH:mm")
                if not reminder.isValid():
                    reminder = None
            else:
                reminder = None
            return (
                title, content, color, tags, pinned, archived, reminder, attached_files, collaborators, drawing
            )

        notes = [deserialize_note(note) for note in data.get("notes", [])]
        archived_notes = [deserialize_note(note) for note in data.get("archived_notes", [])]
        print(f"Loaded {len(notes)} notes and {len(archived_notes)} archived notes from {NOTES_FILE}")
        return notes, archived_notes
    except Exception as e:
        print(f"Error loading notes from {NOTES_FILE}: {str(e)}")
        return [], []

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    test_notes = [
        ("Test Note", "Content here", "#fff3e0", "tag1", True, False, QDateTime.currentDateTime(), ["file1.txt"], ["user1"], "drawing1"),
        ("Short Note", "Less fields"),
    ]
    test_archived = [
        ("Archived Note", "Old content", "#fff3e0", "old", False, True, None, [], [], "")
    ]
    save_notes(test_notes, test_archived)
    loaded_notes, loaded_archived = load_notes()
    print("Loaded Notes:", loaded_notes)
    print("Loaded Archived Notes:", loaded_archived)