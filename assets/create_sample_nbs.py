"""
Generate a sample .nbs file for testing the visualizer.
Creates a melody with multiple instruments. No duplicate (tick, layer) pairs.
"""
import pynbs
import os


def create_sample_nbs(output_path):
    """Create a simple NBS file with a melody."""
    f = pynbs.new_file(
        song_name="Test Melody",
        song_author="NBS Visualizer",
        tempo=10,
        time_signature=4,
    )

    # 4 layers
    f.layers = [
        pynbs.Layer(id=0, name="Melody", lock=False, volume=100, panning=0),
        pynbs.Layer(id=1, name="Bass", lock=False, volume=100, panning=0),
        pynbs.Layer(id=2, name="Bells", lock=False, volume=100, panning=0),
        pynbs.Layer(id=3, name="Harmony", lock=False, volume=100, panning=0),
    ]

    # No custom instruments - use built-in MC instrument IDs
    f.instruments = []

    # --- Section 1: Ascending melody (Harp, layer 0) ---
    melody = [45, 47, 49, 50, 52, 54, 56, 57]  # C major scale
    for i, key in enumerate(melody):
        f.notes.append(pynbs.Note(
            tick=2 + i * 4, layer=0, instrument=0, key=key, velocity=100,
        ))

    # --- Section 1: Descending melody (Harp, layer 0) ---
    for i, key in enumerate(reversed(melody)):
        f.notes.append(pynbs.Note(
            tick=2 + len(melody) * 4 + i * 4, layer=0, instrument=0, key=key, velocity=90,
        ))

    # --- Bass (layer 1) ---
    bass_pattern = [33, 33, 38, 38, 40, 40, 35, 35]
    for i, key in enumerate(bass_pattern):
        f.notes.append(pynbs.Note(
            tick=2 + i * 8, layer=1, instrument=1, key=key, velocity=100,
        ))

    # --- Bell accents (layer 2) ---
    bell_notes = [57, 60, 64, 60, 57, 60, 64, 69]
    for i, key in enumerate(bell_notes):
        f.notes.append(pynbs.Note(
            tick=2 + i * 8, layer=2, instrument=5, key=key, velocity=80,
        ))

    # --- Section 2: Fast harmony (layer 3, different instrument) ---
    # Use ticks that DON'T overlap with section 1's descending melody on layer 0
    # Section 1 descending: ticks 34, 38, 42, 46, 50, 54, 58, 62
    # Section 2 fast: ticks 34, 36, 38, 40, ... on layer 3 (no conflict!)
    for i in range(16):
        f.notes.append(pynbs.Note(
            tick=34 + i * 2, layer=3, instrument=8,  # Guitar
            key=melody[i % len(melody)] + (2 if i % 4 < 2 else 0),
            velocity=100,
        ))

    # --- Final chord (layer 0, 4 simultaneous notes on different layers) ---
    chord_keys = [(0, 45), (1, 52), (2, 57), (3, 64)]
    for layer, key in chord_keys:
        f.notes.append(pynbs.Note(
            tick=68, layer=layer, instrument=0, key=key, velocity=100,
        ))

    f.update_header(version=5)
    f.save(output_path, version=5)
    print(f"Sample NBS saved: {output_path}")
    print(f"  Notes: {len(f.notes)}")
    print(f"  Layers: {len(f.layers)}")
    print(f"  Tempo: {f.header.tempo}")
    print(f"  Song length: {f.header.song_length} ticks")
    print(f"  Duration: ~{f.header.song_length / f.header.tempo:.1f}s")

    # Verify no duplicate (tick, layer) pairs
    seen = set()
    for n in f.notes:
        pair = (n.tick, n.layer)
        assert pair not in seen, f"Duplicate (tick={n.tick}, layer={n.layer})!"
        seen.add(pair)
    print("  No duplicate (tick, layer) pairs - OK")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "uploads", "sample.nbs")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    create_sample_nbs(out)
