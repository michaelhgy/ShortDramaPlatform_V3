"""Frozen release acceptance in a NEW isolated directory; never starts a server."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import traceback
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--require-gpu", action="store_true",
                   help="Select an affine fixture and require real GPU composition")
    p.add_argument('--fullscreen-layers',action='store_true',
                   help='Verify the independent sticker pool, photo quotas and custom parameter values')
    p.add_argument('--actual-scenery-usage',action='store_true',
                   help='Verify only played scenery is reserved, charged and retired')
    p.add_argument('--short-scenery',action='store_true',
                   help='Verify native-HD silent remux and random short clips with shared decoding')
    p.add_argument("--insertions",action="store_true",help="Verify real midroll/endroll on the frozen final renderer")
    args = p.parse_args()
    if args.insertions and args.require_gpu:
        p.error("Insertion composition uses CPU pixel transfer; omit --require-gpu")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ["V2_WORKSPACE_ROOT"] = str(root / "workspace")
    result = {"status": "RUNNING", "workspace": os.environ["V2_WORKSPACE_ROOT"]}

    def save():
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def progress(value, stage):
        with (root / "progress.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "percent": value, "stage": stage}, ensure_ascii=False) + "\n")

    save()
    try:
        from server.release_runtime import probe_v3_resources
        from server.tool_resolver import resolve_ffmpeg, application_resource_root
        from server.ffmpeg_templates.renderer import probe, sha, hidden
        from server.scenery.service import SceneryLibrary
        from server.ffmpeg_templates.service import TemplateMaker
        from server.ffmpeg_finals.renderer import FinalRenderer, load_template
        from server.ffmpeg_templates.config import DEFAULTS
        result["runtime"] = probe_v3_resources()
        result["runtime_root"] = str(application_resource_root())
        if args.short_scenery:
            from tools.release_v3_scenery_probe import verify
            result['short_scenery']=verify(root/'short-scenery')
            save()
        ff = resolve_ffmpeg()
        workspace = root / "workspace"
        data = workspace / "系统数据"
        scenery = SceneryLibrary(workspace, data)
        # Synchronously drive this isolated queue; no application background worker.
        scenery.start = lambda: None
        scenery.original.mkdir(parents=True)
        for number, duration in enumerate([2, 4], 1):
            target = scenery.original / f"原片{number}.mp4"
            subprocess.run([str(ff), "-v", "error", "-n", "-f", "lavfi", "-i",
                            f"testsrc2=size=360x640:rate=30:duration={duration}",
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                            str(target)], check=True, **hidden())
        originals = scenery.scan()["originals"]
        for item in originals:
            crops = [{"x": 0, "y": y, "width": 360, "height": 200} for y in (0, 210, 430)]
            scenery.create(item["id"], crops, str(uuid.uuid4()))
        while scenery.run_next():
            pass
        snap = scenery.snapshot()
        assert snap["counts"]["done"] == 2 and len(snap["assets"]) == 6, snap
        assert not list(scenery.original.glob("*.mp4"))
        result["scenery"] = {"source_jobs": 2, "ready_assets": 6, "originals_deleted": True}
        save()

        maker = TemplateMaker(workspace, data)
        maker.start = lambda: None
        photo_pool=[]
        config = dict(DEFAULTS, duration_seconds=10, duration_jitter=0,
                      effect_count=[1, 1])
        if args.fullscreen_layers:
            from PIL import Image,ImageDraw
            from server.ffmpeg_templates.fullscreen_layers import sticker_catalog
            from server.ffmpeg_templates.parameter_info import field_info
            photos=workspace/'生成资源/真人图片';photos.mkdir(parents=True)
            for i in range(6):
                im=Image.new('RGB',(360+i*12,640),(30+i*30,80+i*15,160-i*10))
                d=ImageDraw.Draw(im);d.ellipse((80,65,260,245),fill=(220,180,145));d.rectangle((60,250,285,620),fill=(60+i*20,70,110))
                im.save(photos/f'fixture_photo_{i+1}.png')
            config.update(duration_seconds=5,height_large_percent=[40,40],height_small_percent=[15,15],
                          mask_percent=[25,25],feather_percent=[0,0],effect_segment_seconds=[1,1],
                          effect_transition_seconds=[7,7],border_width=[20,20],
                          overlay_sticker_enabled=True,overlay_sticker_count=[128,128],
                          photo_layer_enabled=True,photo_usage_limit=1)
            assert len(field_info())==25 and len(sticker_catalog())==383
            result['parameter_contract']={'help_fields':25,'independent_stickers':383,'custom_values':config}
        if args.actual_scenery_usage:
            config.update(duration_seconds=1,scenery_usage_limit=1)
        maker.save_config(config)
        if args.fullscreen_layers:
            maker.photos.refresh()
            with maker.connect() as connection:photo_pool=maker.photos.candidates(connection,1)
        chosen_seed=None
        if args.require_gpu:
            # Select before creating the job so the saved timeline and its
            # actual-playback reservations always belong to the same recipe.
            from server.ffmpeg_templates.renderer import make_plan, read, EFFECTS
            from server.ffmpeg_templates.precompose import affine_asset
            assets = {a["id"]: a for a in read(EFFECTS / "catalog.json")["assets"]}
            materials, _ = maker.scan()
            for seed in range(20261020, 20261120):
                plan = make_plan(config, materials, seed,photos=photo_pool)
                if all(affine_asset(assets[s["asset_id"]]) for s in plan["effects"]["segments"]):
                    chosen_seed=seed
                    result["gpu_fixture_seed"] = seed
                    break
            else:
                raise RuntimeError("No affine template found for GPU release acceptance")
        from unittest.mock import patch
        if chosen_seed is None:maker.create(1,str(uuid.uuid4()))
        else:
            with patch('server.ffmpeg_templates.service.secrets.randbits',return_value=chosen_seed):
                maker.create(1,str(uuid.uuid4()))
        if args.actual_scenery_usage:
            from server.ffmpeg_templates.scenery_usage import scheduled_scenery
            with maker.connect() as connection:
                saved=json.loads(connection.execute('SELECT plan FROM jobs').fetchone()[0])
                reserved={r[0] for r in connection.execute('SELECT source_id FROM reservations')}
            played={m['id'] for m in scheduled_scenery(saved)}
            candidates={m['id']:Path(m['path']) for t in saved['tracks'] for m in t['materials']}
            assert len(candidates)==6 and len(played)==2 and reserved==played
        started = time.perf_counter()
        assert maker.run_next()
        job = maker.snapshot()["jobs"][0]
        if job["status"] != "done":
            raise RuntimeError(job["error"])
        result["template"] = {"seconds": round(time.perf_counter() - started, 3),
                              "path": job["output_path"], "frames": job['seconds']*30}
        if args.actual_scenery_usage:
            with maker.connect() as connection:
                used={r[0] for r in connection.execute('SELECT source_id FROM usages')}
                assert connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]==0
            assert used==played
            assert all(not candidates[i].exists() for i in played)
            assert all(candidates[i].exists() for i in candidates.keys()-played)
            result['actual_scenery_usage']={'candidates':6,'played':2,'reserved':2,'charged':2,
                                           'retired':2,'unplayed_files_preserved':4}
        if args.fullscreen_layers:
            assert not list(photos.iterdir())
            with maker.connect() as connection:
                assert connection.execute('SELECT COUNT(*) FROM photo_usages').fetchone()[0]==6
                assert connection.execute('SELECT COUNT(*) FROM photo_reservations').fetchone()[0]==0
            saved=json.loads((Path(job['package_path'])/'plan.json').read_text(encoding='utf8'))
            assert len(saved['fullscreen_layers']['stickers']['placements'])==128
            result['photo_quota']={'successful_uses':6,'isolated_files_deleted':6,'reservations_remaining':0}
        preview = Path(job["output_path"])
        template = load_template(preview, sha(preview), data)
        source = workspace / "测试主素材.mp4"
        subprocess.run([str(ff), "-v", "error", "-n", "-f", "lavfi", "-i",
                        "testsrc2=size=540x960:rate=30:duration=12",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=12",
                        "-vf", "setsar=1", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", "-c:a", "aac", str(source)],
                       check=True, **hidden())
        final_job={"source_path":str(source),"source_sha256":sha(source),"template":template,"frames":360,"has_audio":True}
        if args.insertions:
            from server.ffmpeg_finals.service import _build_insertions
            ads=workspace/'生成资源'/'引流视频';ads.mkdir(parents=True,exist_ok=True)
            for label,colour,rate,seconds,sound in [('中插01','yellow',25,.6,True),('尾插01','white',30,.5,False)]:
                args_ff=[str(ff),'-v','error','-n','-f','lavfi','-i',f'color={colour}:s=320x240:r={rate}:d={seconds}']
                if sound:args_ff+=['-f','lavfi','-i',f'sine=frequency=880:sample_rate=48000:duration={seconds}','-c:a','aac']
                subprocess.run([*args_ff,'-c:v','libx264','-pix_fmt','yuv420p','-t',str(seconds),str(ads/(label+'.mp4'))],check=True,**hidden())
            strategy={'midroll':{'enabled':True,'mode':'latest','file':'','min_source_duration_seconds':0,'position_start_seconds':3,'position_end_seconds':3},'endroll':{'enabled':True,'mode':'latest','file':''}}
            plan,frames,_=_build_insertions({}, {'id':'release-fixture'},360,sha(source),workspace,{'midroll_endroll_strategy':strategy})
            final_job.update(frames=frames,source_frames=360,source_has_audio=True,insertions=plan)
            result['insertions']=plan
        save()
        renderer = FinalRenderer(data / "fg/release/a1", progress)
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in Path(template["package_path"]).rglob("*") if p.is_file()}
        started = time.perf_counter()
        output = renderer.render(final_job)
        after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in Path(template["package_path"]).rglob("*") if p.is_file()}
        assert before == after, "Final composition changed the completed template"
        check = json.loads((renderer.folder / "check.json").read_text(encoding="utf-8"))
        assert check["template_cache_reused"] and check["new_cache_seconds"] == 0
        assert check["template_repeat_count"] == (final_job['frames']+job['seconds']*30-1)//(job['seconds']*30)
        video = next(s for s in check["media"]["streams"] if s["codec_type"] == "video")
        assert (video["sample_aspect_ratio"], video["display_aspect_ratio"]) == ("1:1", "9:20")
        result["final"] = {"seconds": round(time.perf_counter() - started, 3),
                           "path": str(output), "frames": final_job["frames"], "audio": True,
                           "template_unchanged": True, "check": check}
        if args.insertions:
            import math,struct
            raw=subprocess.check_output([str(ff),'-v','error','-i',str(output),'-vn','-ac','1','-ar','48000','-f','f32le','-'],**hidden())
            samples=struct.unpack('<'+'f'*(len(raw)//4),raw);sound_checks=[]
            for at,frequency in [(1,440),(3.15,880),(4.2,440),(12.8,0)]:
                chunk=samples[int(at*48000):int((at+.15)*48000)]
                rms=math.sqrt(sum(x*x for x in chunk)/len(chunk));hz=sum(a<=0<b for a,b in zip(chunk,chunk[1:]))/.15
                assert rms<.003 if not frequency else rms>.01 and abs(hz-frequency)<18,(at,rms,hz,frequency)
                sound_checks.append({'at':at,'rms':rms,'hz':hz,'expected':frequency})
            assert final_job['frames']==393
            result['insertion_audio_checks']=sound_checks
        if args.require_gpu:
            assert check["acceleration"]["transfer"] == "vulkan", check["acceleration"]
            assert check["acceleration"]["cache_decode"] == "vulkan", check["acceleration"]
            assert check["acceleration"]["source_decode"] == "vulkan", check["acceleration"]
            cpu = FinalRenderer(data / "fg/release/cpu", progress)
            cpu._hardware = {"hevc_cache": False, "vulkan_transfer": False}
            cpu_output = cpu.render({"source_path": str(source), "source_sha256": sha(source),
                                     "template": template, "frames": 360, "has_audio": True})
            result["cpu_compatibility"] = json.loads((cpu.folder / "check.json").read_text(encoding="utf-8"))
            audio_hashes = []
            for media in (output, cpu_output):
                audio_hashes.append(subprocess.check_output(
                    [str(ff), "-v", "error", "-i", str(media), "-map", "0:a:0",
                     "-c", "copy", "-f", "hash", "-hash", "sha256", "-"], **hidden()).decode().strip())
            assert audio_hashes[0] == audio_hashes[1]
            assert before == {p: (p.stat().st_size, p.stat().st_mtime_ns)
                              for p in Path(template["package_path"]).rglob("*") if p.is_file()}
            result["audio_equal"] = True
            result["audio_hashes"] = audio_hashes
        result["status"] = "PASS"
    except Exception:
        result["status"] = "FAIL"
        result["error"] = traceback.format_exc()
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
