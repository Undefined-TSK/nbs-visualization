"""本地渲染脚本：不走Kimi API，本地生成镜头/字幕/弹幕，渲染完整视频。"""
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nbs_visualizer import extract_tracks, render_video


def generate_local_script(tracks, total_seconds, group_names):
    """根据歌曲结构本地生成 kimi_script（镜头+字幕+弹幕）。"""
    rng = random.Random(42)

    cameras = []
    subtitles = []
    danmaku = []

    num_groups = len(group_names)

    # ---- 镜头脚本：每4-6s切换一次焦点 ----
    t = 0.0
    phase = "intro"
    while t < total_seconds:
        if t < 8.0:
            cam_type, focus = "wide", "all"
        elif t < total_seconds * 0.85:
            roll = rng.random()
            if roll < 0.5:
                cam_type = "group"
                focus = rng.randint(0, num_groups - 1)
            elif roll < 0.75:
                cam_type = "close"
                track = rng.choice(tracks)
                focus = track.layer_id
            else:
                cam_type, focus = "wide", "all"
        else:
            cam_type, focus = "wide", "all"

        cameras.append({"time": round(t, 2), "type": cam_type, "focus": focus})
        t += rng.uniform(4.0, 6.0)

    # 最后回到全景
    cameras.append({"time": total_seconds, "type": "wide", "focus": "all"})

    # ---- 字幕：按段落生成 ----
    section_texts = [
        (0, "旋律登场"),
        (total_seconds * 0.08, "主题展开"),
        (total_seconds * 0.18, "节奏加入"),
        (total_seconds * 0.30, "副歌高潮"),
        (total_seconds * 0.45, "间奏过渡"),
        (total_seconds * 0.55, "第二段"),
        (total_seconds * 0.70, "副歌再现"),
        (total_seconds * 0.85, "尾奏收束"),
    ]
    for start, text in section_texts:
        subtitles.append({
            "text": text,
            "time": round(start, 1),
            "duration": 4.0,
        })

    # ---- 弹幕：随机MC风格评论 ----
    danmaku_pool = [
        "666", "好听!", "这段太燃了", "前方高能", "nice!",
        "经典!", "循环播放", "封神之作", "泪目了", "太强了",
        "前方注意", "节奏起来了", "旋律杀我", "这段好听到爆", "爷青回",
        "awsl", "神仙编曲", "节奏组太稳了", "贝斯好评", "铜管太帅了",
    ]
    t = 3.0
    while t < total_seconds - 2.0:
        text = rng.choice(danmaku_pool)
        danmaku.append({"time": round(t, 1), "text": text})
        t += rng.uniform(2.5, 6.0)

    return {
        "cameras": cameras,
        "subtitles": subtitles,
        "danmaku": danmaku,
    }


if __name__ == "__main__":
    nbs_file = "uploads/YMCA.nbs"
    audio_file = "uploads/YMCA.mp3"
    output_path = "outputs/YMCA.mp4"

    tracks, header = extract_tracks(nbs_file, use_kimi=False)
    tps = header.tempo
    total_seconds = header.song_length / tps

    group_names = []
    seen = set()
    for tr in tracks:
        if tr.group not in seen:
            seen.add(tr.group)
            group_names.append(tr.group)

    print(f"Song: {header.song_name}")
    print(f"Duration: {total_seconds:.1f}s | Tracks: {len(tracks)} | Groups: {group_names}")

    script = generate_local_script(tracks, total_seconds, group_names)
    print(f"Generated: {len(script['cameras'])} cameras, {len(script['subtitles'])} subtitles, {len(script['danmaku'])} danmaku")

    def progress_cb(p, msg):
        print(f"  [{p*100:.0f}%] {msg}")

    final = render_video(
        nbs_file, output_path,
        audio_file=audio_file,
        use_kimi=False,
        kimi_script_override=script,
        progress_callback=progress_cb,
    )
    print(f"\nDone: {final}")
