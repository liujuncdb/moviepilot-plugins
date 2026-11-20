"""横版 16:9 设计基元：直接复用竖版基元，保证两族同一套字号/对比度标准。"""
from ..portrait._kit import (  # noqa: F401
    CJK_FONT, SERIF_FONT, SERIF_BOLD_FONT, load_font, has_cjk, hex_rgba, title_font,
    micro_font, tracked_width, draw_tracked, wrap_lines, fit_title, line_height,
    draw_block, tune_color, dominant_color, duotone, grain, vignette, gradient_band,
    torn_mask, soft_plate, paste_masked, drop_shadow, hairline, micro_line, clamp_text,
    seed_of, cover_fit, relative_luminance, contrast_ratio, region_luminance,
    text_color_for, text_color_on_color, pick_ref, collect_posters, meta_text,
    palette_accent, contain, photo_card, rotated, paste_card, paper_tone, deep_tone, scrim,
    card_size, soft_grade, soft_paper, tinted_deep, paper_gradient, tune_color,
)
