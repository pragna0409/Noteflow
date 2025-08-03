from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import os
import socket

NOTES_FILE = "notes.json"
DRIVE_FILE_NAME = "noteflow_notes.json"

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