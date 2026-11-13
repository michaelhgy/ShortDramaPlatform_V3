import assert from 'node:assert/strict';
import test from 'node:test';
import {getOptimizationHealth} from './optimizationHealth.ts';

test('optimization health includes 50 percent in critical and 20 percent in healthy',()=>{
  for(const [rate,level] of [[0,'healthy'],[19.9,'healthy'],[20,'healthy'],[20.1,'warning'],[25,'warning'],[49.9,'warning'],[50,'critical'],[55.6,'critical'],[100,'critical']] as const)
    assert.equal(getOptimizationHealth(rate),level);
});
