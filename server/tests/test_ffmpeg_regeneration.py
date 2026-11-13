"""Explicit re-generation is distinct from same-plan technical retries."""
import json
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import pytest

from server import v2_file_service as business
from server.tests.test_ffmpeg_insertions import environment, resource, settings


def rows(env):
    with closing(env.lib.connect()) as conn:
        return [dict(row) for row in conn.execute('SELECT * FROM final_jobs ORDER BY rowid')]


@pytest.mark.parametrize('status', ['done', 'error', 'cancelled'])
def test_single_regenerates_with_latest_global_instead_of_first_snapshot(environment, status):
    env = environment
    env.composer.create(env.task['id'])
    before = rows(env)
    identity = before[0]['id']
    with closing(env.lib.connect()) as conn:
        conn.execute('UPDATE final_jobs SET status=? WHERE id=?', (status, identity)); conn.commit()
    ad = resource(env)
    business.update_v2_settings(settings())
    assert env.composer.regenerate(identity=identity) == {'regenerated_count': 1}
    after = rows(env)
    plan = json.loads(after[0]['plan'])
    assert after[0]['status'] == 'waiting'
    assert plan['insertions']['midroll']['path'] == str(ad)
    assert plan['frames'] == 600
    assert plan['target'] == json.loads(before[0]['plan'])['target']
    assert plan['template'] == json.loads(before[0]['plan'])['template']
    assert after[1] == before[1]
    history = list((env.composer.root / identity[:12] / 'regeneration_history').glob('*.json'))
    assert len(history) == 1 and json.loads(history[0].read_text(encoding='utf-8'))['plan'] == before[0]['plan']
    with pytest.raises(ValueError, match='只可'):
        env.composer.regenerate(identity=identity)


def test_regeneration_reads_current_task_material_and_latest_ad(environment):
    env = environment
    resource(env); business.update_v2_settings(settings())
    env.composer.create(env.task['id'])
    before = rows(env); first, second = before
    with closing(env.lib.connect()) as conn:
        conn.execute("UPDATE final_jobs SET status='cancelled'"); conn.commit()
    business.update_task_insertion_strategy(env.task['id'], {'midroll': {'enabled': False}, 'endroll': {'enabled': True}})
    business.update_material_insertion_strategy(first['material_id'], {'midroll': {'enabled': True}, 'endroll': {'enabled': False}})
    ad = resource(env, '中插99.mp4'); tail = resource(env, '尾插03.mp4')
    assert env.composer.regenerate(task_id=env.task['id'])['regenerated_count'] == 2
    plans = [json.loads(row['plan']) for row in rows(env)]
    assert plans[0]['insertions']['midroll']['path'] == str(ad)
    assert plans[0]['insertions']['endroll']['status'] == 'disabled'
    assert plans[1]['insertions']['midroll']['status'] == 'disabled'
    assert plans[1]['insertions']['endroll']['path'] == str(tail)


def test_batch_deletes_completed_immediately_while_paused_and_keeps_names_and_usage(environment):
    env = environment
    env.composer.create(env.task['id']); env.composer.run_next()
    before = rows(env); old = Path(before[0]['output_path'])
    previous_media_version = business.get_task_details(env.task['id'])['videos'][0]['output_media_version']
    env.composer.action('pause')
    resource(env); business.update_v2_settings(settings())
    assert env.composer.regenerate(task_id=env.task['id'])['regenerated_count'] == 2
    assert env.composer.snapshot()['paused']
    assert not env.composer.run_next()
    assert not old.exists()
    env.composer.action('resume')
    assert env.composer.run_next() and env.composer.run_next()
    after = rows(env)
    assert all(row['status'] == 'done' for row in after)
    assert old.is_file()
    assert all(Path(row['output_path']).is_file() and row['output_path'] == json.loads(row['plan'])['target'] for row in after)
    assert not list(old.parent.glob('*_R*.mp4'))
    with closing(env.lib.connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM outputs').fetchone()[0] == 2
        assert len(env.lib.used_drama_keys(conn, env.template_id)) == 1
        assert dict(conn.execute('SELECT output_id,output_path FROM outputs')) == {row['id']: row['output_path'] for row in after}
    detail = business.get_task_details(env.task['id'])
    assert all(video['output_duration_seconds'] == 20 for video in detail['videos'])
    assert detail['videos'][0]['output_media_version'] != previous_media_version
    assert {video['output_path'] for video in detail['videos']} == {row['output_path'] for row in after}
    assert env.composer.regenerate(identity=after[0]['id'])['regenerated_count'] == 1
    assert json.loads(rows(env)[0]['plan'])['target'] == str(old)


@pytest.mark.parametrize('defect', ['missing_ad', 'last_material', 'running', 'released', 'template', 'source_changed'])
def test_batch_errors_are_atomic_and_do_not_modify_existing_jobs(environment, defect):
    env = environment
    env.finish_pair()
    if defect == 'missing_ad': business.update_v2_settings(settings())
    if defect == 'last_material':
        identity = rows(env)[-1]['material_id']
        with closing(business.connection()) as conn:
            conn.execute("UPDATE production_files SET status='missing' WHERE id=?", (identity,)); conn.commit()
    if defect == 'running':
        with closing(env.lib.connect()) as conn:
            conn.execute("UPDATE final_jobs SET status='running' WHERE id=?", (rows(env)[-1]['id'],)); conn.commit()
    if defect == 'released':
        with closing(business.connection()) as conn:
            conn.execute("UPDATE production_tasks SET release_status='registered' WHERE id=?", (env.task['id'],)); conn.commit()
    if defect == 'template': env.template.unlink()
    if defect == 'source_changed': env.materials[-1].write_bytes(b'changed')
    before = rows(env)
    with pytest.raises(ValueError): env.composer.regenerate(task_id=env.task['id'])
    assert rows(env) == before
    assert all(Path(row['output_path']).is_file() for row in before)


def test_regeneration_leaves_unrecorded_r02_file_alone(environment):
    env = environment
    before = env.finish_pair()
    old = Path(before[0]['output_path'])
    unrelated = old.with_name(old.stem + '_R02.mp4')
    unrelated.write_bytes(b'user existing output')
    env.composer.regenerate(identity=before[0]['id'])
    assert json.loads(rows(env)[0]['plan'])['target'] == str(old)
    assert not old.exists()
    env.composer.run_next()
    assert unrelated.read_bytes() == b'user existing output'


def test_failed_regeneration_has_no_old_video_and_technical_retry_keeps_plan(environment):
    env = environment
    before = env.finish_pair(); old = Path(before[0]['output_path'])
    old_cache = Path(before[0]['package_path']) / 'final.mp4'
    assert old_cache.is_file()
    env.composer.regenerate(identity=before[0]['id'])
    assert not old.exists() and not old_cache.exists()
    assert rows(env)[0]['output_path'] == '' and rows(env)[0]['package_path'] == ''
    assert business.get_task_details(env.task['id'])['videos'][0]['output_exists'] is False
    plan = rows(env)[0]['plan']; renderer = env.composer.render
    env.composer.render = lambda *args: (_ for _ in ()).throw(RuntimeError('fixture failure'))
    env.composer.run_next()
    assert rows(env)[0]['status'] == 'error'
    assert not old.exists()
    env.composer.action('retry', before[0]['id'])
    assert json.loads(rows(env)[0]['plan']) == json.loads(plan)
    env.composer.render = renderer; env.composer.run_next()
    assert rows(env)[0]['status'] == 'done' and old.is_file()


def test_old_publication_receipt_cannot_reuse_same_path_for_new_generation(environment):
    env = environment
    before = env.finish_pair(); job = before[0]
    target = Path(job['output_path']); content = target.read_bytes()
    receipt = env.composer.root / job['id'][:12] / 'publication.json'
    old_receipt = receipt.read_bytes()
    env.composer.regenerate(identity=job['id'])
    assert not target.exists() and not receipt.exists()
    # Even identical bytes at the same path cannot reuse the prior generation receipt.
    target.write_bytes(content); receipt.write_bytes(old_receipt)
    env.composer.run_next()
    assert rows(env)[0]['status'] == 'error'
    assert '不属于' in rows(env)[0]['error']


def test_legacy_recorded_r02_and_original_removed_without_new_suffix(environment):
    env = environment
    before = env.finish_pair(); job = before[0]; original = Path(job['output_path'])
    legacy = original.with_name(original.stem + '_R02.mp4'); legacy.write_bytes(b'old R02')
    folder = env.composer.root / job['id'][:12] / 'regeneration_history'; folder.mkdir()
    (folder/'legacy.json').write_text(json.dumps(job), encoding='utf8')
    plan=json.loads(job['plan']); plan.update(target=str(legacy), regeneration=2)
    with closing(env.lib.connect()) as conn:
        conn.execute('UPDATE final_jobs SET plan=?,output_path=? WHERE id=?',(json.dumps(plan),str(legacy),job['id'])); conn.commit()
    env.composer.regenerate(identity=job['id'])
    assert not original.exists() and not legacy.exists()
    assert json.loads(rows(env)[0]['plan'])['target'] == str(original)
    env.composer.run_next()
    assert original.is_file() and not legacy.exists()


def test_delete_failure_stops_job_and_does_not_start_batch(environment):
    env = environment
    before=env.finish_pair(); old=Path(before[0]['output_path'])
    unlink=Path.unlink
    def fail_old(path, *args, **kwargs):
        if path == old: raise PermissionError('occupied')
        return unlink(path, *args, **kwargs)
    with patch.object(Path, 'unlink', fail_old):
        with pytest.raises(ValueError, match='删除旧成品失败'):
            env.composer.regenerate(task_id=env.task['id'])
    after=rows(env)
    assert after[0]['status']=='error' and after[1]==before[1]
    assert not env.composer.run_next()
    env.composer.regenerate(identity=before[0]['id'])
    assert not old.exists()


def test_unowned_canonical_name_is_not_deleted(environment):
    env=environment
    before=env.finish_pair(); job=before[0]; original=Path(job['output_path'])
    legacy=original.with_name(original.stem+'_R02.mp4'); original.rename(legacy)
    plan=json.loads(job['plan']); plan.update(target=str(legacy),regeneration=2)
    with closing(env.lib.connect()) as conn:
        conn.execute('UPDATE final_jobs SET plan=?,output_path=? WHERE id=?',(json.dumps(plan),str(legacy),job['id'])); conn.commit()
    original.write_bytes(b'unrelated')
    with pytest.raises(ValueError,match='其他文件占用'): env.composer.regenerate(identity=job['id'])
    assert original.read_bytes()==b'unrelated' and legacy.is_file()


def test_http_routes_reach_regeneration_without_using_same_plan_retry(environment):
    from server.ffmpeg_finals.http import handle
    from unittest.mock import Mock
    env = environment; env.finish_pair(); handler = Mock(); identity = rows(env)[0]['id']
    with patch('server.ffmpeg_finals.http.get_composer', return_value=env.composer):
        assert handle(handler, 'POST', '/api/v3/final-composition/jobs/' + identity + '/regenerate', {})
        assert handler._json.call_args.args[0] == 200
        assert handle(handler, 'POST', '/api/v3/final-composition/regenerate', {'task_id': env.task['id']})
        assert handler._json.call_args.args[1] == {'regenerated_count': 2}


def test_no_jobs_is_an_error_not_a_new_implicit_batch(environment):
    with pytest.raises(ValueError, match='先批量合成'):
        environment.composer.regenerate(task_id=environment.task['id'])
