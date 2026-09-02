"""The frozen worker entry points used by the production runtime."""

PRODUCTION_WORKERS = (
    "server.template_engine.generate_v2_template",
    "server.final_engine.scripts.run_jianying_composition_batch",
    "server.final_engine.scripts.replenish_jianying_bgm",
    "server.final_engine.scripts.register_ready_bgm",
    "server.final_engine.scripts.detect_opening_cover",
    "server.final_engine.scripts.detect_tail_guidance",
    "server.final_engine.scripts.detect_black_bars",
    "server.final_engine.scripts.detect_drama_title_region",
    "server.final_engine.scripts.generate_composition_from_detection_reports",
    "server.final_engine.scripts.prepare_clean_viral_proxy",
    "server.final_engine.scripts.generate_jianying59_composition_draft",
    "server.final_engine.scripts.prepare_finished_video_export",
)
