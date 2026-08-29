import pathlib
from PIL import Image, ImageDraw, ImageOps


def draw_boxes(image_path, boxes, output_path=None):
    """Draw labelled bounding boxes onto an image and save the result.

    boxes: list of dicts, each with a "label" and a "box_2d" of four values
    [y_min, x_min, y_max, x_max] normalised to 0-1000. Returns the path of the
    saved image.
    """
    img = Image.open(image_path)
    # Apply the EXIF orientation before drawing so the pixels match the view the
    # normalised box coordinates refer to (prevents shifted/rotated boxes on
    # photos that carry an orientation flag).
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    colors = ["red", "blue", "green", "orange", "purple", "cyan"]

    # Border thickness scales with image size so boxes stay clearly visible on
    # large photos (e.g. 3024x4032).
    border_w = max(8, round(min(w, h) * 0.008))

    for i, item in enumerate(boxes):
        if not isinstance(item, dict):
            continue

        label  = item.get("label", f"Object {i+1}")
        coords = (item.get("box_2d") or item.get("box2d") or
                  item.get("box") or item.get("bounding_box") or
                  item.get("bbox") or [])
        color  = colors[i % len(colors)]

        if not isinstance(coords, list) or len(coords) != 4:
            continue
        if not all(isinstance(v, (int, float)) for v in coords):
            continue

        # [y_min, x_min, y_max, x_max] normalised 0-1000 -> pixel coordinates
        y_min, x_min, y_max, x_max = coords
        x1 = int(min(x_min, x_max) / 1000 * w)
        y1 = int(min(y_min, y_max) / 1000 * h)
        x2 = int(max(x_min, x_max) / 1000 * w)
        y2 = int(max(y_min, y_max) / 1000 * h)

        # Clamp to image bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        draw.rectangle([x1, y1, x2, y2], outline=color, width=border_w)
        text_y = max(y1 - 24, 0)
        draw.rectangle([x1, text_y, x1 + len(label) * 8 + 8, text_y + 22], fill=color)
        draw.text((x1 + 4, text_y + 2), label, fill="white")

    if output_path is None:
        output_path = pathlib.Path(image_path).with_stem(pathlib.Path(image_path).stem + "_annotated")
    img.save(output_path)
    return output_path
