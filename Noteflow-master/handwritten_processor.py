import os
import base64
from groq import Groq
import pdf2image
from PIL import Image
import io

GROQ_API_KEY = "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"

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def pdf_to_images(pdf_path):
    try:
        images = pdf2image.convert_from_path(pdf_path, dpi=300)
        return images
    except Exception as e:
        print(f"Error converting PDF: {e}")
        return []

def extract_handwritten_text(file_path):
    if not os.path.exists(file_path):
        return "Error: File does not exist"
    file_extension = os.path.splitext(file_path)[1].lower()
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.pdf'}
    if file_extension not in allowed_extensions:
        return "Error: Unsupported file format. Use PNG, JPG, JPEG, or PDF"
    client = Groq(api_key=GROQ_API_KEY)
    try:
        if file_extension == '.pdf':
            images = pdf_to_images(file_path)
            if not images:
                return "Error: Could not process PDF"
            extracted_text = ""
            for i, image in enumerate(images):
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
                response = client.chat.completions.create(
                    model="llama-3.2-11b-vision-preview",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract the handwritten text from this image."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                            ]
                        }
                    ],
                    max_tokens=500
                )
                text = response.choices[0].message.content.strip()
                extracted_text += f"\n[Page {i+1}]\n{text}"
            return extracted_text.strip()
        else:
            base64_image = image_to_base64(file_path)
            response = client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract the handwritten text from this image."},
                            {"type": "image_url", "image_url": {"url": f"data:image/{file_extension[1:]};base64,{base64_image}"}}
                        ]
                    }
                ],
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error processing file: {str(e)}"

def summarize_handwritten_text(text, client):
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant that summarizes handwritten notes."},
                {"role": "user", "content": f"Summarize the following handwritten text:\n\n{text}"}
            ],
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error summarizing text: {str(e)}"