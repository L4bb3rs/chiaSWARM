import hashlib
import io
from PIL import Image, ImageDraw
import base64
import json
from io import BytesIO
import itertools


class OutputProcessor:
    def __init__(self, output_list, main_content_type):
        self.outputs = []
        self.other_outputs = {}
        self.output_list = output_list
        self.main_content_type = main_content_type

    def add_outputs(self, images):
        self.outputs.extend(images)

    def add_other_outputs(self, name, images):
        self.other_outputs[name] = images

    def get_results(self):
        results = {}
        if "primary" in self.output_list:
            primary_result = post_process(self.outputs)
            primary_result_buffer = image_to_buffer(
                primary_result, self.main_content_type
            )
            results["primary"] = make_result(
                primary_result_buffer, primary_result_buffer, self.main_content_type
            )

        for key, images in self.other_outputs.items():
            result = post_process(images)
            result_buffer = image_to_buffer(result, self.main_content_type)
            results[key] = make_result(
                result_buffer,
                result_buffer,
                self.main_content_type,
            )

        return results


def make_result(_buffer, thumb, content_type):
    if thumb is None:
        thumb = image_from_text(content_type, (100, 100), 1)
        thumb = image_to_buffer(thumb, "image/jpeg", "web_low")
    else:
        thumb = make_thumbnail(thumb)

    return {
        "blob": base64.b64encode(_buffer.getvalue()).decode("UTF-8"),
        "content_type": content_type,
        "thumbnail": base64.b64encode(thumb.getvalue()).decode("UTF-8"),
        "sha256_hash": hashlib.sha256(_buffer.getvalue()).hexdigest(),
    }


def make_text_result(string):
    caption = {"caption": string}
    thumb = image_from_text("text/plain", (100, 100), 1)
    thumb = image_to_buffer(thumb, "image/jpeg", "web_low")
    return {
        "blob": base64.b64encode(bytes(json.dumps(caption), "utf-8")).decode("UTF-8"),
        "content_type": "application/json",
        "thumbnail": base64.b64encode(thumb.getvalue()).decode("UTF-8"),
        "sha256_hash": hashlib.sha256(string.encode()).hexdigest(),
    }


def make_thumbnail(_buffer):
    if not isinstance(_buffer, BytesIO):
        _buffer = BytesIO(_buffer)

    image = Image.open(_buffer).convert("RGB")  # type: ignore
    image.thumbnail((100, 100), Image.Resampling.LANCZOS)
    return image_to_buffer(image, "image/jpeg", "web_low")


def image_from_text(text, size=(512, 512), color=0):
    image = Image.new(mode="RGB", size=size, color=color)
    draw = ImageDraw.Draw(image)

    draw.multiline_text((5, 5), text)
    return image


def post_process(image_list):
    num_images = len(image_list)
    if num_images == 1:
        image = image_list[0]
    elif num_images == 2:
        image = image_grid(image_list, 1, 2)
    elif num_images <= 4:
        image = image_grid(image_list, 2, 2)
    elif num_images <= 6:
        image = image_grid(image_list, 2, 3)
    elif num_images <= 9:
        image = image_grid(image_list, 3, 3)
    else:
        raise ValueError(
            f"Too many images ({num_images}) for post-processing. Maximum supported images: 9"
        )

    return image


def image_grid(image_list, rows, cols) -> Image.Image:
    w, h = image_list[0].size
    grid = Image.new("RGB", size=(cols * w, rows * h))
    indices = list(itertools.product(range(rows), range(cols)))

    for i, index in enumerate(indices[: len(image_list)]):
        grid.paste(image_list[i], box=(index[1] * w, index[0] * h))

    return grid


def image_to_buffer(image, content_type, quality="web_high"):
    if content_type.startswith("image"):
        _buffer = io.BytesIO()
        if content_type == "image/png":
            image.save(_buffer, format="PNG")
        elif content_type == "image/jpeg":
            image.save(
                _buffer, format="JPEG", quality=quality, optimize=True, progressive=True
            )
        else:
            raise ValueError(f"Invalid image format: {content_type}")

        _buffer.seek(0)
        return _buffer

    raise ValueError(f"Unsupported content type: {content_type}")
