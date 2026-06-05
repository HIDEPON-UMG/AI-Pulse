"""AI-Pulse OGP / Twitter Card 画像生成（1200x630 PNG）。

Twitter / Facebook は SVG og:image を解決しないため、リリース時にラスタライズ済み PNG を
``static/og-image.png`` として生成・コミットする。SSG ビルド（generate_pages）はこの PNG を
``_copy_assets`` で site/ に流すだけで、自前ではラスタライズしない（依存最小化）。

ラスタライズは Scoop の resvg CLI に委譲する。理由:
- DESIGN.md のロゴ・配色トークンと一次同期したいので、ソースは SVG が自然。
- Pillow を AI-Pulse の .venv に追加すると依存が増える（収集系コードでは不要）。
- resvg は既に scoop 経由で導入済み（``shutil.which('resvg')``）。

subprocess 直呼びはプロジェクト全体で禁止（pyproject の banned-api lint）。本モジュールは
``tools._proc.run.quiet_run`` を経由して resvg を起動する。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from _proc.run import quiet_run  # noqa: E402

STATIC_DIR = ROOT / "static"
OUT_PNG = STATIC_DIR / "og-image.png"
OUT_SVG = STATIC_DIR / "og-image.svg"

# --- DESIGN.md / theme.css と一次同期する hex トークン ---
# `_head.html.j2` で `<meta name="theme-color" content="#101113">` と揃える。
BG = "#101113"
FG = "#EEEFF1"
FG_SUB = "#AAACB1"
ACCENT = "#1F95D6"
# 7 レンズ accent 色（DESIGN.md "カテゴリアクセント" の hex 正規化値順）
LENS_COLORS = [
    "#70ADFE",  # model
    "#48D8DF",  # editor
    "#BEA3FF",  # physical
    "#E291EE",  # media
    "#66DC9E",  # agent
    "#F5C25F",  # infra
    "#FF8977",  # policy
]

W, H = 1200, 630


def _logo_svg(cx: int, cy: int, size: int) -> str:
    """中心 (cx, cy) に size×size のロゴを描く SVG 断片。

    元 icon.svg の 512×512 viewBox を size に等倍縮小して埋め込む。
    icon.svg を編集したら本関数の path 群も同期する（一次ソースは icon.svg）。
    """
    s = size / 512
    x0 = cx - size // 2
    y0 = cy - size // 2
    return (
        f'<g transform="translate({x0},{y0}) scale({s})">'
        f'<rect width="512" height="512" rx="104" fill="{ACCENT}"/>'
        '<path d="M200 144 L136 88 M264 392 L344 336" fill="none" stroke="#fff" '
        'stroke-width="19" stroke-linecap="round" opacity="0.55"/>'
        '<path d="M72 264 H160 L200 144 L264 392 L320 264 H440" fill="none" stroke="#fff" '
        'stroke-width="40" stroke-linejoin="round" stroke-linecap="round"/>'
        '<circle cx="136" cy="88" r="24" fill="#fff"/>'
        '<circle cx="344" cy="336" r="24" fill="#fff"/>'
        '<circle cx="200" cy="144" r="35" fill="#fff"/>'
        '<circle cx="264" cy="392" r="35" fill="#fff"/>'
        f'<circle cx="200" cy="144" r="15" fill="{ACCENT}"/>'
        f'<circle cx="264" cy="392" r="15" fill="{ACCENT}"/>'
        '</g>'
    )


def build_svg() -> str:
    """OGP 1200x630 の SVG ソースを組み立てて返す。"""
    logo_size = 280
    logo_cx = 240
    logo_cy = H // 2 - 8  # 縦中央・底部レンズバー分わずかに上
    logo = _logo_svg(logo_cx, logo_cy, logo_size)

    # 底部 7 レンズ色アクセントバー（4px 厚）。
    bar_h = 12
    bar_y = H - bar_h
    bar_w = W / len(LENS_COLORS)
    bars = "".join(
        f'<rect x="{i * bar_w:.2f}" y="{bar_y}" width="{bar_w:.2f}" '
        f'height="{bar_h}" fill="{c}"/>'
        for i, c in enumerate(LENS_COLORS)
    )

    # ワードマーク + サブタイトル + 補助行（明朝・等幅）。
    # `text-anchor="start"` で x = 左端基準。フォントは theme.css と同等のフォールバック列で
    # resvg が OS フォント解決する（Noto Serif JP / Yu Mincho / serif）。
    word_x = 430
    text = (
        f'<text x="{word_x}" y="290" font-family="Noto Serif JP, Yu Mincho, serif" '
        f'font-size="138" font-weight="900" fill="{FG}" letter-spacing="-4">'
        f'AI<tspan fill="{ACCENT}">-</tspan>Pulse</text>'
        f'<text x="{word_x}" y="362" font-family="Noto Serif JP, Yu Mincho, serif" '
        f'font-size="36" font-weight="500" fill="{FG_SUB}">'
        '生成AIニュースの分析サイト兼DB</text>'
        f'<text x="{word_x}" y="416" font-family="JetBrains Mono, Consolas, monospace" '
        f'font-size="20" font-weight="400" fill="{FG_SUB}" letter-spacing="2">'
        '7 LENSES × DEEP KARTE</text>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">'
        f'<rect width="{W}" height="{H}" fill="{BG}"/>'
        f'{logo}{text}{bars}'
        '</svg>'
    )


def main() -> int:
    svg = build_svg()
    OUT_SVG.write_text(svg, encoding="utf-8")
    resvg = shutil.which("resvg")
    if not resvg:
        print(
            "[gen_og_image] resvg が PATH に無い。"
            "`scoop install resvg` で導入してから再実行してください。",
            file=sys.stderr,
        )
        return 1
    # 明示的に出力解像度を指定し DPI 起因のサイズずれを排除。
    r = quiet_run(
        [resvg, "--width", str(W), "--height", str(H), str(OUT_SVG), str(OUT_PNG)],
        check=False,
    )
    if r.returncode != 0:
        print(
            f"[gen_og_image] resvg 失敗 (rc={r.returncode}): {r.stderr.strip()}",
            file=sys.stderr,
        )
        return r.returncode
    print(
        f"[gen_og_image] {OUT_PNG.relative_to(ROOT)} を生成 "
        f"({OUT_PNG.stat().st_size:,} bytes / {W}x{H})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
