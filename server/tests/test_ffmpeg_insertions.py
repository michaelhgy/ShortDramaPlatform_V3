"""FFmpeg insertion plans, inheritance and business persistence in temporary databases."""
import json
from contextlib import closing
from unittest.mock import patch
import pytest
from server import v2_file_service as business
from server.ffmpeg_finals.service import _build_insertions, _insertion_strategy_for
from server.tests import test_ffmpeg_finals as fixtures

@pytest.fixture
def environment():
    fixture=fixtures.FinalTests()
    fixture.setUp()
    try: yield fixture
    finally: fixture.tearDown()


def settings(**mid):
    return {business.ENGINE_PARAMETER_KEY:{'midroll':{'enabled':True,'mode':'latest','file':'','min_source_duration_seconds':5,'position_start_seconds':2,'position_end_seconds':3,**mid},'endroll':{'enabled':False,'mode':'latest','file':''}}}


def resource(env,name='中插01.mp4'):
    path=business.WORKSPACE/'生成资源'/'引流视频'/name
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'ad')
    return path


def test_untouched_global_preserves_ffmpeg_no_insertions(environment):
    plan,frames,audio=_build_insertions({}, {'id':'m'},300,'hash',business.WORKSPACE,{})
    assert frames==300 and not audio
    assert [s['kind'] for s in plan['segments']]==['source']


def test_below_threshold_and_empty_window_skip_without_resource(environment):
    for frames,status,rule in [(149,'skipped_short_source',settings()),(150,'skipped_invalid_window',settings(position_start_seconds=6,position_end_seconds=8))]:
        plan,total,_=_build_insertions({}, {'id':'m'},frames,'hash',business.WORKSPACE,rule)
        assert plan['midroll']['status']==status and total==frames


def test_equal_threshold_inserts_and_preserves_every_source_frame(environment):
    resource(environment)
    plan,total,_=_build_insertions({}, {'id':'m'},150,'hash',business.WORKSPACE,settings())
    assert plan['midroll']['status']=='inserted' and total==450
    left,ad,right=plan['segments']
    assert left['frames']==right['source_start_frame'] and left['frames']+right['frames']==150
    assert 60<=left['frames']<=90
    second,_,_=_build_insertions({}, {'id':'m'},150,'hash',business.WORKSPACE,settings())
    assert plan==second


def test_window_intersection_excludes_last_and_zero_frames(environment):
    resource(environment)
    plan,_,_=_build_insertions({}, {'id':'m'},150,'hash',business.WORKSPACE,settings(position_start_seconds=4.9,position_end_seconds=100))
    assert 147<=plan['segments'][0]['frames']<=149


def test_inheritance_is_per_field_and_per_slot(environment):
    global_rule=settings();global_rule[business.ENGINE_PARAMETER_KEY]['endroll']['enabled']=True
    task={'midroll_endroll_strategy':json.dumps({'midroll':{'enabled':False}})}
    material={'midroll_endroll_strategy':json.dumps({'endroll':{'enabled':False}})}
    actual=_insertion_strategy_for(task,material,global_rule)
    assert not actual['midroll']['enabled'] and not actual['endroll']['enabled']
    assert actual['midroll']['position_end_seconds']==3
    global_rule[business.ENGINE_PARAMETER_KEY]['midroll']['position_end_seconds']=4
    assert _insertion_strategy_for(task,material,global_rule)['midroll']['position_end_seconds']==4
    assert _insertion_strategy_for(task,{},global_rule)['endroll']['enabled']


def test_persistence_readback_restore_and_single_material_scope(environment):
    env=environment
    detail=business.get_task_details(env.task['id']);first,second=detail['materials']
    business.update_task_insertion_strategy(env.task['id'],{'midroll':{'enabled':False}})
    detail=business.update_material_insertion_strategy(first['id'],{'endroll':{'enabled':False}})
    assert detail['midroll_endroll_strategy']=={'midroll':{'enabled':False}}
    by_id={item['id']:item for item in detail['materials']}
    assert by_id[first['id']]['insertion_strategy']=={'endroll':{'enabled':False}}
    assert by_id[second['id']]['insertion_strategy'] is None
    detail=business.update_material_insertion_strategy(first['id'],None)
    assert not detail['materials'][0]['insertion_strategy']
    assert business.update_task_insertion_strategy(env.task['id'],None)['midroll_endroll_strategy'] is None


def test_schema_11_migration_retains_materials(environment):
    with closing(business.connection()) as conn:
        before=conn.execute('SELECT id,file_path FROM production_files').fetchall()
        conn.execute('ALTER TABLE production_files DROP COLUMN midroll_endroll_strategy')
        conn.execute('PRAGMA user_version=11');conn.commit()
    business.DATABASE_INITIALIZED_PATH=None
    with closing(business.connection()) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==12
        after=conn.execute('SELECT id,file_path,midroll_endroll_strategy FROM production_files').fetchall()
        assert [tuple(r) for r in before]==[tuple(r)[:2] for r in after]
        assert all(r[2]=='' for r in after)


def test_missing_ad_does_not_create_partial_batch(environment):
    business.update_v2_settings(settings())
    with pytest.raises(ValueError,match='缺少'):
        environment.composer.create(environment.task['id'])
    assert environment.composer.snapshot()['jobs']==[]


def test_retry_uses_snapshot_even_after_global_changes(environment):
    env=environment;resource(env)
    business.update_v2_settings(settings())
    env.composer.create(env.task['id'])
    original=env.composer.snapshot()['jobs'][0];identity=original['id']
    with closing(env.lib.connect()) as conn:
        before=json.loads(conn.execute('SELECT plan FROM final_jobs WHERE id=?',(identity,)).fetchone()[0])
        conn.execute("UPDATE final_jobs SET status='error' WHERE id=?",(identity,));conn.commit()
    business.update_v2_settings({business.ENGINE_PARAMETER_KEY:{'midroll':{'enabled':False,'mode':'latest','file':''},'endroll':{'enabled':False,'mode':'latest','file':''}}})
    resource(env,'中插99.mp4')
    env.composer.action('retry',identity)
    with closing(env.lib.connect()) as conn: after=json.loads(conn.execute('SELECT plan FROM final_jobs WHERE id=?',(identity,)).fetchone()[0])
    assert before['insertions']==after['insertions']
    assert after['insertions']['midroll']['path'].endswith('中插01.mp4')
    detail=business.get_task_details(env.task['id'])
    assert all(v['output_duration_seconds']==20 for v in detail['videos'])


def test_automatic_recovers_when_missing_ad_is_added(environment):
    env=environment;business.update_v2_settings(settings())
    env.composer.auto_enabled=True
    assert not env.composer.automatic_tick()
    assert env.composer.auto_error
    resource(env)
    assert env.composer.automatic_tick()
    assert not env.composer.auto_error

@pytest.mark.parametrize('payload',[{'midroll':{'enabled':'no'}},{'midroll':{'position_start_seconds':float('nan')}},{'midroll':{'position_start_seconds':5,'position_end_seconds':2}},{'endroll':{'position_end_seconds':5}},{'other':{}}])
def test_invalid_override_is_rejected(payload):
    with pytest.raises(ValueError): business.normalize_insertion_override(payload)


def test_disabled_missing_locked_media_does_not_block_submission(environment):
    rule=settings()
    rule[business.ENGINE_PARAMETER_KEY]['midroll'].update(enabled=False,mode='locked',file='')
    plan,frames,_=_build_insertions({}, {'id':'m'},300,'hash',business.WORKSPACE,rule)
    assert plan['midroll']['status']=='disabled' and frames==300


def test_released_task_cannot_modify_task_or_material_policy(environment):
    task_id=environment.task['id']
    material=business.get_task_details(task_id)['materials'][0]
    with closing(business.connection()) as conn:
        conn.execute("UPDATE production_tasks SET release_status='registered' WHERE id=?",(task_id,));conn.commit()
    with pytest.raises(ValueError): business.update_task_insertion_strategy(task_id,{'midroll':{'enabled':False}})
    with pytest.raises(ValueError): business.update_material_insertion_strategy(material['id'],{'midroll':{'enabled':False}})


def test_mutated_insertion_is_rejected_before_rendering(environment):
    from server.ffmpeg_finals.renderer import FinalRenderer
    from server.ffmpeg_templates.renderer import sha
    source=environment.materials[0];ad=resource(environment)
    expected=sha(ad);ad.write_bytes(b'changed ad')
    renderer=object.__new__(FinalRenderer);renderer.progress=lambda *args:None
    job={'source_path':str(source),'source_sha256':sha(source),'template':{},'insertions':{'segments':[{'kind':'insertion','path':str(ad),'sha256':expected,'slot':'midroll'}]}}
    with pytest.raises(ValueError,match='素材已变化'):renderer.render(job)
