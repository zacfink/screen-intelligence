"""Find a piece of on-screen text with Tesseract and return where to click it."""
import cv2
import pyautogui
import pytesseract
from thefuzz import fuzz

NEARBY = 80  # px in the 2x image: hits this close together are one cluster


def to_screen(img, x, y):
    """Scale a point in the (resized) screenshot back to pyautogui's screen coordinates."""
    img_h, img_w = img.shape
    screen_w, screen_h = pyautogui.size()
    return round(x * screen_w / img_w, 2), round(y * screen_h / img_h, 2)


def mean_box(cluster):
    return [round(sum(float(hit[k]) for hit in cluster) / len(cluster), 2) for k in range(5)]


def best_match(hits):
    """hits are Tesseract rows [left, top, width, height, conf, text, ...]. Averages each cluster
    of nearby hits and returns the box [left, top, width, height, conf] with the highest confidence."""
    try:
        if not hits:
            return None
        if len(hits) == 1 or hits[0][:2] == hits[1][:2]:
            return [int(v) for v in hits[0][:4]]
        clusters = []
        for hit in hits:
            cx, cy = int(hit[0]) + int(hit[2]) // 2, int(hit[1]) + int(hit[3]) // 2
            near = [o for o in hits if o != hit and abs(cx - int(o[0])) < NEARBY and abs(cy - int(o[1])) < NEARBY]
            if near:
                clusters.append([hit] + near)
        return max(map(mean_box, clusters), key=lambda box: box[4]) if clusters else None
    except (ValueError, IndexError):  # Tesseract's header row or a blank line matched
        return None


def find_text(path, text):
    img = cv2.imread(str(path))
    img = cv2.resize(img, None, fx=2, fy=2)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    hits = []
    for psm in [6, 11, 12]:
        data = pytesseract.image_to_data(img, config=f"--oem 3 --psm {psm}", lang="eng")
        for row in data.split("\n"):
            cols = row.split("\t")
            for word in text.split():
                if word in cols[-1] or fuzz.ratio(word, cols[-1]) > 50:
                    hits.append(cols[6:])

    box = best_match(hits)
    if not box or not box[2] or not box[3]:
        return None  # no match with a real bounding box
    return to_screen(img, box[0] + box[2] / 2, box[1] + box[3] / 2)
