"""
Generate Minecraft-style pixel-art textures programmatically using Pillow.
All textures are 16x16 (or multiples thereof) to match Minecraft's aesthetic.
No copyrighted assets are used - everything is generated from scratch.
"""

from PIL import Image, ImageDraw
import os
import random

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "textures")

# Instrument definitions: (name, base_color, secondary_color, accent_color)
INSTRUMENTS = {
    "harp":        ((130, 90, 50),  (100, 70, 35),  (200, 160, 80)),
    "bass":        ((60, 50, 45),   (40, 35, 30),   (90, 80, 70)),
    "bd":          ((70, 65, 60),   (50, 45, 40),   (110, 100, 90)),
    "snare":       ((200, 190, 160),(170, 160, 130), (230, 220, 200)),
    "hat":         ((180, 200, 220),(150, 170, 200), (220, 230, 240)),
    "bell":        ((230, 200, 80), (200, 170, 50),  (255, 230, 120)),
    "flute":       ((200, 180, 150),(170, 150, 120), (240, 220, 190)),
    "chime":       ((180, 230, 240),(150, 200, 230), (220, 250, 255)),
    "guitar":      ((160, 100, 60), (130, 80, 40),   (200, 140, 90)),
    "xylophone":   ((240, 230, 200),(210, 200, 170), (255, 250, 230)),
    "iron_xylo":   ((200, 200, 205),(170, 170, 180), (230, 230, 235)),
    "cow_bell":    ((140, 100, 60), (110, 80, 45),   (170, 130, 80)),
    "didgeridoo":  ((180, 120, 50), (150, 90, 35),   (210, 140, 70)),
    "bit":         ((80, 200, 120), (60, 170, 90),   (120, 240, 150)),
    "banjo":       ((220, 200, 100),(190, 170, 70),  (250, 230, 130)),
    "pling":       ((230, 220, 80), (200, 190, 50),  (255, 250, 120)),
}


def add_noise(draw, size, base_color, noise_range=15):
    """Add pixel-level noise to simulate Minecraft texture style."""
    noise_img = Image.new("RGB", (size, size), base_color)
    pixels = noise_img.load()
    for y in range(size):
        for x in range(size):
            r, g, b = base_color
            n = random.randint(-noise_range, noise_range)
            pixels[x, y] = (
                max(0, min(255, r + n)),
                max(0, min(255, g + n)),
                max(0, min(255, b + n)),
            )
    return noise_img


def make_note_block_texture(size=16):
    """Generate a Minecraft-style note block texture."""
    img = Image.new("RGB", (size, size), (0, 0, 0))
    pixels = img.load()

    # Base wood color with noise
    base = (130, 90, 50)
    dark = (100, 70, 35)
    light = (160, 110, 60)
    hole = (40, 28, 15)

    for y in range(size):
        for x in range(size):
            # Border frame (darker)
            if x < 2 or x >= size - 2 or y < 2 or y >= size - 2:
                n = random.randint(-10, 10)
                pixels[x, y] = (
                    max(0, min(255, dark[0] + n)),
                    max(0, min(255, dark[1] + n)),
                    max(0, min(255, dark[2] + n)),
                )
            # Center hole (where the note comes out)
            elif 5 <= x <= 10 and 5 <= y <= 10:
                n = random.randint(-5, 5)
                pixels[x, y] = (
                    max(0, min(255, hole[0] + n)),
                    max(0, min(255, hole[1] + n)),
                    max(0, min(255, hole[2] + n)),
                )
            else:
                n = random.randint(-15, 15)
                pixels[x, y] = (
                    max(0, min(255, base[0] + n)),
                    max(0, min(255, base[1] + n)),
                    max(0, min(255, base[2] + n)),
                )
    return img


def make_instrument_texture(name, colors, size=16):
    """Generate a Minecraft-style instrument block texture."""
    base, dark, accent = colors
    img = Image.new("RGB", (size, size), (0, 0, 0))
    pixels = img.load()

    for y in range(size):
        for x in range(size):
            # Top highlight (lighter)
            if y < 2:
                n = random.randint(-10, 15)
                c = accent
            # Bottom shadow (darker)
            elif y >= size - 2:
                n = random.randint(-15, 5)
                c = dark
            # Left/right edges
            elif x < 1 or x >= size - 1:
                n = random.randint(-12, 8)
                c = dark
            else:
                n = random.randint(-15, 15)
                c = base

            pixels[x, y] = (
                max(0, min(255, c[0] + n)),
                max(0, min(255, c[1] + n)),
                max(0, min(255, c[2] + n)),
            )

    # Add a small "note" indicator in center
    cx, cy = size // 2, size // 2
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if 0 <= cx + dx < size and 0 <= cy + dy < size:
                pixels[cx + dx, cy + dy] = accent

    return img


def make_note_particle(color, size=8):
    """Generate a floating note particle texture."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw a small diamond/note shape
    cx, cy = size // 2, size // 2
    r = size // 3

    points = [
        (cx, cy - r),
        (cx + r, cy),
        (cx, cy + r),
        (cx - r, cy),
    ]
    draw.polygon(points, fill=color + (220,))

    # Add glow
    for i in range(2):
        r2 = r + i + 1
        alpha = 60 - i * 30
        points2 = [
            (cx, cy - r2),
            (cx + r2, cy),
            (cx, cy + r2),
            (cx - r2, cy),
        ]
        draw.polygon(points2, outline=color + (alpha,))

    return img


def make_sky_gradient(width=1280, height=720):
    """Generate a Minecraft-style sky background gradient."""
    img = Image.new("RGB", (width, height), (0, 0, 0))
    pixels = img.load()

    # Minecraft sky: light blue at top, slightly lighter at horizon
    top_color = (135, 206, 235)
    bottom_color = (180, 220, 240)

    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        for x in range(width):
            n = random.randint(-3, 3)
            pixels[x, y] = (
                max(0, min(255, r + n)),
                max(0, min(255, g + n)),
                max(0, min(255, b + n)),
            )
    return img


def make_grid_overlay(width, height, cell_size=40):
    """Generate a subtle grid overlay for the piano roll visualization."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for x in range(0, width, cell_size):
        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 15), width=1)
    for y in range(0, height, cell_size):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 15), width=1)

    return overlay


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    random.seed(42)  # Reproducible textures

    # Generate note block texture
    print("Generating note block texture...")
    nb = make_note_block_texture(16)
    nb = nb.resize((64, 64), Image.NEAREST)
    nb.save(os.path.join(ASSETS_DIR, "note_block.png"))

    # Generate instrument textures
    for name, colors in INSTRUMENTS.items():
        print(f"Generating instrument texture: {name}")
        tex = make_instrument_texture(name, colors, 16)
        tex = tex.resize((64, 64), Image.NEAREST)
        tex.save(os.path.join(ASSETS_DIR, f"instrument_{name}.png"))

    # Generate note particles in different colors
    note_colors = [
        (255, 80, 80),    # Red
        (80, 255, 80),    # Green
        (80, 80, 255),    # Blue
        (255, 255, 80),   # Yellow
        (255, 80, 255),   # Magenta
        (80, 255, 255),   # Cyan
        (255, 180, 80),   # Orange
        (180, 80, 255),   # Purple
    ]
    for i, color in enumerate(note_colors):
        particle = make_note_particle(color, 16)
        particle = particle.resize((32, 32), Image.NEAREST)
        particle.save(os.path.join(ASSETS_DIR, f"particle_{i}.png"))

    # Generate sky background
    print("Generating sky background...")
    sky = make_sky_gradient(1280, 720)
    sky.save(os.path.join(ASSETS_DIR, "sky_bg.png"))

    # Generate grid overlay
    print("Generating grid overlay...")
    grid = make_grid_overlay(1280, 720, 40)
    grid.save(os.path.join(ASSETS_DIR, "grid_overlay.png"))

    print(f"\nAll textures generated in {ASSETS_DIR}")
    print(f"Files: {os.listdir(ASSETS_DIR)}")


if __name__ == "__main__":
    main()
