"""Verify an existing DB copy; --apply performs only additive feature-table repair."""
import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import v2_file_service as files

def state(conn):
    tables=[r[0]for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    result={}
    for table in tables:
        safe=table.replace('"','""');rows=conn.execute(f'SELECT * FROM "{safe}"').fetchall()
        result[table]={'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False,default=repr,separators=(',',':')).encode()).hexdigest()}
    return result

def migrate(conn):
    conn.execute('BEGIN IMMEDIATE')
    version=conn.execute('PRAGMA user_version').fetchone()[0]
    if version not in (5,6):raise RuntimeError('本修复仅适用于结构版本5或6')
    before=state(conn);files._upgrade_feature_schema(conn);after=state(conn)
    if any(after.get(k)!=v for k,v in before.items()):
        conn.rollback();raise RuntimeError('原有记录校验不一致，已回滚')
    conn.commit()
    return {'before_version':version,'after_version':conn.execute('PRAGMA user_version').fetchone()[0],
        'unchanged_tables':len(before),'added_tables':sorted(set(after)-set(before)),'before':before,'after':after}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    database=Path(args.database).resolve()
    if not database.is_file():raise RuntimeError('数据库不存在')
    out=ROOT/'local-test-output/cover-schema-repair-20261026'/datetime.now().strftime('%H%M%S')
    out.mkdir(parents=True,exist_ok=False)
    backup=out/'before.sqlite';copydb=out/'verification.sqlite'
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as source, closing(sqlite3.connect(backup)) as dest:
        source.backup(dest)
        images={row[0]:hashlib.sha256(Path(row[0]).read_bytes()).hexdigest() for row in source.execute("SELECT cover_path FROM drama_profiles WHERE cover_path<>''") if Path(row[0]).is_file()}
    with closing(sqlite3.connect(backup)) as src,closing(sqlite3.connect(copydb)) as dest:src.backup(dest)
    with closing(sqlite3.connect(copydb)) as conn:verified=migrate(conn)
    result={'database':str(database),'backup':str(backup),'copy_verified':verified,'applied':False,'original_images':images}
    if args.apply:
        with closing(sqlite3.connect(database,timeout=30)) as conn:result['live']=migrate(conn)
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in images.items()):raise RuntimeError('原图片校验发生变化')
        result['applied']=True
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'copy_verified':True,'applied':result['applied'],'unchanged_existing_tables':verified['unchanged_tables'],'new_tables':verified['added_tables'],'original_images':len(images),'backup':str(backup),'report':str(out/'result.json')},ensure_ascii=False))

if __name__=='__main__':main()
