import base64


def encodeImage(image_path="../takenScreenshots/screen.png"):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
